from __future__ import annotations

import os
import re
import hashlib
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Iterable
from xml.etree import ElementTree

ProgressCallback = Callable[[int | None, str], None]


@dataclass(frozen=True)
class FirmwareInfo:
    path: str
    file_type: str
    min_address: int | None = None
    max_address: int | None = None
    start_address: int | None = None

    @property
    def size(self) -> int:
        if self.min_address is None or self.max_address is None:
            return 0
        return self.max_address - self.min_address + 1


@dataclass(frozen=True)
class FlashOptions:
    probe_uid: str = ""
    target: str = ""
    pack_path: str = ""
    algorithm_path: str = ""
    firmware_path: str = ""
    address: str = ""
    frequency: str = "4000000"
    connect_mode: str = "under-reset"
    chip_erase: bool = True
    verify_after_download: bool = True
    reset_after_download: bool = True
    flash_start: int | None = None
    flash_size: int | None = None


class PyOcdBackend:
    _PROGRESS_RE = re.compile(r"(?<!\d)(100(?:\.0+)?|[1-9]?\d(?:\.\d+)?)\s*%")
    _LIST_TIMEOUT_SECONDS = 10.0
    _COMMAND_TIMEOUT_SECONDS = 300.0

    def __init__(self) -> None:
        self._python = sys.executable
        self._frozen = bool(getattr(sys, "frozen", False))

    def list_probes(self) -> tuple[int, str]:
        return self._run(["list"], timeout_seconds=self._LIST_TIMEOUT_SECONDS)

    def check_probe(self, options: FlashOptions) -> tuple[int, str]:
        probe_error = self._probe_error(options)
        if probe_error:
            return probe_error
        return 0, ""

    def show_pack_targets(self, pack_path: str) -> tuple[int, str]:
        args = ["list", "--targets"]
        if pack_path:
            args.extend(["--pack", pack_path])
        return self._run(args)

    def connect(self, options: FlashOptions, check_probe: bool = True) -> tuple[int, str]:
        if check_probe:
            probe_error = self._probe_error(options)
            if probe_error:
                return probe_error
        args = ["commander", *self._connection_args(options), "-c", "status"]
        return self._run_flash_command(args, options)

    def erase(self, options: FlashOptions, progress_callback: ProgressCallback | None = None, check_probe: bool = True) -> tuple[int, str]:
        if check_probe:
            probe_error = self._probe_error(options)
            if probe_error:
                return probe_error
        args = ["erase", *self._connection_args(options), "--chip"]
        return self._run_flash_command(args, options, progress_callback)

    def download(self, options: FlashOptions, progress_callback: ProgressCallback | None = None, check_probe: bool = True) -> tuple[int, str]:
        if check_probe:
            probe_error = self._probe_error(options)
            if probe_error:
                return probe_error
        firmware = self._required_file(options.firmware_path, "固件文件")
        args = ["load", *self._connection_args(options)]
        if firmware.suffix.lower() == ".bin":
            args.extend(["-a", self._validate_bin_file(firmware, options)])
        # 全片擦除是下载流程中的独立阶段；load 只做写入所需的扇区擦除。
        # pyOCD 默认会在 load 结束时复位，并在断开会话时恢复运行。
        # 两者都关闭，确保检验完成前目标始终保持停止。
        args.extend(["-e", "sector", "--no-reset", "-O", "resume_on_disconnect=false", str(firmware)])
        return self._run_flash_command(args, options, progress_callback)

    def verify(self, options: FlashOptions, progress_callback: ProgressCallback | None = None, check_probe: bool = True) -> tuple[int, str]:
        if check_probe:
            probe_error = self._probe_error(options)
            if probe_error:
                return probe_error
        firmware = self._required_file(options.firmware_path, "固件文件")
        if firmware.suffix.lower() in {".elf", ".axf"}:
            return self._verify_elf(firmware, options, progress_callback)
        if firmware.suffix.lower() == ".hex":
            return self._verify_hex(firmware, options, progress_callback)
        address = self._validate_bin_file(firmware, options)
        args = ["commander", *self._connection_args(options), "-c", f"compare {address} {self._quote_commander_path(firmware)}"]
        return self._run_compare_command(args, options, progress_callback)

    @staticmethod
    def _required_bin_address(value: str) -> str:
        address = value.strip().replace("_", "")
        if not address:
            raise ValueError("BIN 文件不包含加载地址，请填写起始地址。")
        if not address.lower().startswith("0x"):
            address = f"0x{address}"
        if not re.fullmatch(r"0[xX][0-9a-fA-F]+", address):
            raise ValueError(f"起始地址格式无效：{value}。请输入十六进制地址。")
        parsed = int(address, 16)
        if parsed < 0:
            raise ValueError(f"起始地址不能为负数：{value}")
        return f"0x{parsed:08X}"

    def _validate_bin_file(self, firmware: Path, options: FlashOptions) -> str:
        address = self._required_bin_address(options.address)
        start = int(address, 16)
        size = firmware.stat().st_size
        if size <= 0:
            raise ValueError(f"BIN 文件为空：{firmware}")
        if options.flash_start is not None and options.flash_size is not None and options.flash_size > 0:
            flash_start = options.flash_start
            flash_end = flash_start + options.flash_size - 1
            end = start + size - 1
            if start < flash_start or end > flash_end:
                raise ValueError(
                    "BIN 地址超出当前芯片 Flash 范围："
                    f"BIN 0x{start:08X}-0x{end:08X}，"
                    f"Flash 0x{flash_start:08X}-0x{flash_end:08X}。"
                )
        return address

    def _verify_hex(self, firmware: Path, options: FlashOptions, progress_callback: ProgressCallback | None = None) -> tuple[int, str]:
        temporary_files: list[Path] = []
        outputs: list[str] = []
        try:
            segments = self._hex_data_segments(firmware)
            total_size = sum(len(data) for _address, data in segments) or 1
            completed_size = 0
            for address, data in segments:
                temporary = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
                temporary.write(data)
                temporary.close()
                path = Path(temporary.name)
                temporary_files.append(path)
                args = ["commander", *self._connection_args(options), "-c", f"compare 0x{address:08X} {self._quote_commander_path(path)}"]

                def segment_progress(percent: int | None, text: str) -> None:
                    if progress_callback is None:
                        return
                    if percent is None:
                        progress_callback(None, text)
                        return
                    mapped = int((completed_size + len(data) * (percent / 100.0)) * 100 / total_size)
                    progress_callback(min(100, max(0, mapped)), text)

                code, output = self._run_compare_command(args, options, segment_progress)
                outputs.append(output)
                if code != 0:
                    return code, "\n\n".join(outputs)
                completed_size += len(data)
                if progress_callback:
                    progress_callback(int(completed_size * 100 / total_size), "")
            return 0, "\n\n".join(outputs)
        finally:
            for path in temporary_files:
                path.unlink(missing_ok=True)

    def _verify_elf(self, firmware: Path, options: FlashOptions, progress_callback: ProgressCallback | None = None) -> tuple[int, str]:
        from elftools.elf.elffile import ELFFile

        temporary_files: list[Path] = []
        outputs: list[str] = []
        try:
            with firmware.open("rb") as stream:
                elf = ELFFile(stream)
                segments = [
                    (int(segment["p_paddr"]), bytes(segment.data()))
                    for segment in elf.iter_segments()
                    if segment.header.p_type == "PT_LOAD" and segment.header.p_filesz != 0
                ]
            if not segments:
                raise ValueError("ELF/AXF 文件没有可检验的加载段。")
            total_size = sum(len(data) for _address, data in segments) or 1
            completed_size = 0
            for address, data in segments:
                temporary = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
                temporary.write(data)
                temporary.close()
                path = Path(temporary.name)
                temporary_files.append(path)
                args = ["commander", *self._connection_args(options), "-c", f"compare 0x{address:08X} {self._quote_commander_path(path)}"]

                def segment_progress(percent: int | None, text: str) -> None:
                    if progress_callback is None:
                        return
                    if percent is None:
                        progress_callback(None, text)
                        return
                    mapped = int((completed_size + len(data) * (percent / 100.0)) * 100 / total_size)
                    progress_callback(min(100, max(0, mapped)), text)

                code, output = self._run_compare_command(args, options, segment_progress)
                outputs.append(output)
                if code != 0:
                    return code, "\n\n".join(outputs)
                completed_size += len(data)
                if progress_callback:
                    progress_callback(int(completed_size * 100 / total_size), "")
            return 0, "\n\n".join(outputs)
        finally:
            for path in temporary_files:
                path.unlink(missing_ok=True)

    def reset_run(self, options: FlashOptions, check_probe: bool = True) -> tuple[int, str]:
        if check_probe:
            probe_error = self._probe_error(options)
            if probe_error:
                return probe_error
        args = ["commander", *self._connection_args(options), "-c", "reset", "-c", "go"]
        return self._run_flash_command(args, options)

    def detect_chip(self, options: FlashOptions, check_probe: bool = True) -> tuple[int, str]:
        if check_probe:
            probe_error = self._probe_error(options)
            if probe_error:
                return probe_error
        args = ["commander", *self._connection_args(options), "-c", "status", "-c", "show target"]
        return self._run_flash_command(args, options)

    def find_flash_algorithm(self, pack_path: str, target: str) -> str:
        pack = self._required_path(pack_path, "Pack 文件或目录")
        target_key = self._normalize_target(target)
        if not target_key:
            return ""
        if pack.is_file():
            return self._find_flash_algorithm_in_pack(pack, target_key)
        return self._find_flash_algorithm_in_dir(pack, target_key)

    def _connection_args(self, options: FlashOptions, connect_mode: str | None = None) -> list[str]:
        args: list[str] = []
        if options.probe_uid:
            args.extend(["--uid", options.probe_uid.strip()])
        if options.target:
            args.extend(["--target", options.target.strip()])
        if options.frequency:
            args.extend(["--frequency", options.frequency.strip()])
        mode = options.connect_mode.strip() if connect_mode is None else connect_mode.strip()
        if mode:
            if mode not in {"halt", "pre-reset", "under-reset", "attach"}:
                raise ValueError(f"pyOCD 连接模式无效：{mode}")
            args.extend(["--connect", mode])
        if options.pack_path:
            args.extend(["--pack", str(self._required_path(options.pack_path, "Pack 文件或目录"))])
        algorithm = Path(options.algorithm_path).expanduser()
        if algorithm.is_file() and algorithm.suffix.lower() == ".flm":
            args.extend(["--script", str(self._manual_algorithm_script(algorithm))])
        return args

    def _run_flash_command(
        self,
        args: list[str],
        options: FlashOptions,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[int, str]:
        code, output = self._run(args, progress_callback)
        if self.has_no_probe(output):
            message = "未检测到 DAP 调试器，请插入调试器后点击刷新，再重新执行。"
            return code or 1, f"{output}\n\n{message}"
        if self.has_unknown_target(output):
            message = "当前目标芯片未被 pyOCD 识别；请确认已选择正确芯片、芯片包仍在芯片库中，并确认目标芯片型号和固件匹配。"
            return code or 1, f"{output}\n\n{message}"
        if self.has_no_target(output):
            message = "DAP 调试器已连接，但无法连接目标芯片；请确认目标板已上电、SWD 接线正确、芯片未损坏，并尝试降低 DAP 频率后重试。"
            return code or 1, f"{output}\n\n{message}"
        if self._has_communication_error(output):
            message = f"DAP 调试器已连接，但与目标芯片通信失败；当前频率为 {options.frequency.strip() or '默认值'}。请检查 SWD 接线、目标供电、复位脚状态，并尝试降低 DAP 频率后重试。"
            return code or 1, f"{output}\n\n{message}"
        return code, output

    def _probe_error(self, options: FlashOptions) -> tuple[int, str] | None:
        code, output = self.list_probes()
        probes = self.extract_probe_ids(output)
        if self.has_no_probe(output):
            message = "未检测到 DAP 调试器，请插入调试器后点击刷新，再重新执行。"
            return code or 1, f"{output}\n\n{message}"
        if not probes:
            if code != 0:
                return code, output
            message = "未检测到 DAP 调试器，请插入调试器后点击刷新，再重新执行。"
            return 1, f"{output}\n\n{message}"

        selected_uid = self.normalize_probe_uid(options.probe_uid)
        if selected_uid:
            connected = {self.normalize_probe_uid(probe) for probe in probes}
            if selected_uid not in connected:
                message = f"当前选择的 DAP 调试器已断开：{selected_uid}。请点击刷新后重新选择调试器。"
                return 1, f"{output}\n\n{message}"
        return None

    @staticmethod
    def _has_communication_error(output: str) -> bool:
        return any(
            marker in output.lower()
            for marker in (
                "swd/jtag communication failure",
                "unexpected ack",
                "transfer fault",
                "memory transfer failed",
                "error reading ap#",
                "ap transfer error",
                "unable to read",
            )
        )

    @staticmethod
    def has_no_probe(output: str) -> bool:
        return "no available debug probes are connected" in output.lower()

    @staticmethod
    def has_unknown_target(output: str) -> bool:
        lower = output.lower()
        return "target type" in lower and "not recognized" in lower

    @staticmethod
    def has_no_target(output: str) -> bool:
        return any(
            marker in output.lower()
            for marker in (
                "error while initing target",
                "debugportsetup",
                "no cores were discovered",
                "unable to connect to target",
                "target not connected",
            )
        )

    def _run_compare_command(
        self,
        args: list[str],
        options: FlashOptions,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[int, str]:
        code, output = self._run_flash_command(args, options, progress_callback)
        if code == 0 and "bytes match" not in output.lower():
            return 1, output + "\n\n检验未返回数据一致结果。"
        return code, output

    @staticmethod
    def _manual_algorithm_script(algorithm: Path) -> Path:
        algorithm = algorithm.resolve()
        digest = hashlib.sha256(str(algorithm).encode("utf-8")).hexdigest()[:16]
        script_dir = Path(tempfile.gettempdir()) / "DAPFlashTool"
        script_dir.mkdir(parents=True, exist_ok=True)
        script = script_dir / f"flm_override_{digest}.py"
        source = (
            "import logging\n"
            "from pyocd.core.memory_map import MemoryType\n\n"
            f"FLM_PATH = {str(algorithm)!r}\n\n"
            "LOG = logging.getLogger(__name__)\n\n"
            "def will_connect(board):\n"
            "    regions = list(board.target.memory_map.iter_matching_regions(type=MemoryType.FLASH))\n"
            "    if not regions:\n"
            "        raise RuntimeError('目标没有可应用手动 FLM 的 Flash 区域')\n"
            "    region = next((item for item in regions if item.is_boot_memory), regions[0])\n"
            "    region.flm = FLM_PATH\n"
            "    LOG.info('使用手动 Flash 算法：%s', FLM_PATH)\n"
        )
        if not script.is_file() or script.read_text(encoding="utf-8") != source:
            script.write_text(source, encoding="utf-8")
        return script

    def _run(
        self,
        args: Iterable[str],
        progress_callback: ProgressCallback | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[int, str]:
        command = self._command(list(args))
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        output_parts: list[str] = []
        timeout = self._COMMAND_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=creationflags,
            )
        except FileNotFoundError as exc:
            return 127, f"无法启动 Python 或 pyOCD：{exc}"

        output_queue: Queue[str | None] = Queue()

        def read_output() -> None:
            try:
                if process.stdout is None:
                    return
                while True:
                    chunk = process.stdout.read(1)
                    if chunk == "":
                        break
                    output_queue.put(chunk)
            finally:
                output_queue.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()

        timed_out = False
        finished_reading = process.stdout is None
        scan_tail = ""
        last_percent: int | None = None
        started_at = time.monotonic()
        while not finished_reading:
            if process.poll() is None and timeout and time.monotonic() - started_at > timeout:
                timed_out = True
                process.kill()

            try:
                chunk = output_queue.get(timeout=0.1)
            except Empty:
                continue
            if chunk is None:
                finished_reading = True
                continue
            output_parts.append(chunk)
            if progress_callback:
                scan_tail = (scan_tail + chunk)[-160:]
                matches = self._PROGRESS_RE.findall(scan_tail)
                if matches:
                    percent = min(100, max(0, int(float(matches[-1]))))
                    if percent != last_percent:
                        progress_callback(percent, "")
                        last_percent = percent

        returncode = process.wait()
        reader.join(timeout=1.0)
        output = "".join(output_parts).replace("\r\n", "\n").replace("\r", "\n").strip()
        if timed_out:
            if output:
                output = f"{output}\n\npyOCD 命令超时，已强制结束。"
            else:
                output = "pyOCD 命令超时，已强制结束。"
            returncode = returncode if returncode not in (0, None) else 124
        if not output:
            output = "命令执行完成，没有额外输出。"
        return returncode, f"$ {self._format_command(command)}\n\n{output}"

    @staticmethod
    def extract_probe_ids(output: str) -> list[str]:
        probes: list[str] = []
        for line in output.splitlines():
            row = re.match(r"\s*(\d+)\s+(.+?)\s{2,}(\S+)\s+(.+)\s*$", line)
            if row and row.group(3).lower() != "id":
                probes.append(f"{row.group(3)}  |  {row.group(2).strip()}  |  {row.group(4).strip()}")
                continue

            lower = line.lower()
            if not any(marker in lower for marker in ("unique id", "uid", "serial")):
                continue
            fallback = re.search(r"\b([0-9A-Fa-f]{8,})\b", line)
            if fallback:
                probes.append(fallback.group(1))
        return sorted(dict.fromkeys(probes))

    @staticmethod
    def normalize_probe_uid(value: str) -> str:
        return value.split("|", 1)[0].strip()

    @staticmethod
    def extract_pack_targets(output: str) -> list[str]:
        targets: list[str] = []
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("$", "-", "#")):
                continue
            if re.search(r"\b(Target|Part|Vendor|Source)\b", stripped, re.IGNORECASE):
                continue
            columns = re.split(r"\s{2,}", stripped)
            for column in columns:
                value = column.strip()
                if re.fullmatch(r"[A-Za-z0-9_.-]{3,}", value) and not value.isdigit():
                    targets.append(value)
                    break
        return sorted(dict.fromkeys(targets))

    @staticmethod
    def analyze_firmware(path_value: str) -> FirmwareInfo:
        path = PyOcdBackend._required_file(path_value, "固件文件")
        suffix = path.suffix.lower().lstrip(".") or "unknown"
        if suffix == "hex":
            return PyOcdBackend._analyze_hex(path)
        if suffix in {"elf", "axf"}:
            return PyOcdBackend._analyze_elf(path, suffix)
        return FirmwareInfo(path=str(path), file_type=suffix)

    @staticmethod
    def _analyze_elf(path: Path, file_type: str) -> FirmwareInfo:
        from elftools.elf.elffile import ELFFile

        with path.open("rb") as stream:
            elf = ELFFile(stream)
            segments = [
                (int(segment["p_paddr"]), int(segment.header.p_filesz))
                for segment in elf.iter_segments()
                if segment.header.p_type == "PT_LOAD" and segment.header.p_filesz != 0
            ]
            entry = int(elf.header.e_entry)
        if not segments:
            return FirmwareInfo(str(path), file_type, start_address=entry)
        minimum = min(address for address, _size in segments)
        maximum = max(address + size - 1 for address, size in segments)
        return FirmwareInfo(str(path), file_type, minimum, maximum, entry)

    @staticmethod
    def format_firmware_info(info: FirmwareInfo) -> str:
        if info.min_address is None or info.max_address is None:
            return f"固件类型：{info.file_type.upper()}，无法从文件中读取标准地址范围。"
        start = f"，入口地址：0x{info.start_address:08X}" if info.start_address is not None else ""
        return f"固件类型：{info.file_type.upper()}，地址范围：0x{info.min_address:08X}-0x{info.max_address:08X}，大小：{info.size} 字节{start}。"

    @staticmethod
    def _analyze_hex(path: Path) -> FirmwareInfo:
        upper_linear = 0
        upper_segment = 0
        min_address: int | None = None
        max_address: int | None = None
        start_address: int | None = None
        with path.open("r", encoding="ascii", errors="replace") as file:
            for line_number, raw_line in enumerate(file, 1):
                line = raw_line.strip()
                if not line:
                    continue
                if not line.startswith(":") or len(line) < 11:
                    raise ValueError(f"HEX 格式错误，第 {line_number} 行。")
                byte_count = int(line[1:3], 16)
                offset = int(line[3:7], 16)
                record_type = int(line[7:9], 16)
                data = line[9 : 9 + byte_count * 2]
                if record_type == 0x00:
                    base = (upper_linear << 16) + (upper_segment << 4)
                    absolute = base + offset
                    if byte_count:
                        end_address = absolute + byte_count - 1
                        min_address = absolute if min_address is None else min(min_address, absolute)
                        max_address = end_address if max_address is None else max(max_address, end_address)
                elif record_type == 0x02:
                    upper_segment = int(data, 16)
                    upper_linear = 0
                elif record_type == 0x04:
                    upper_linear = int(data, 16)
                    upper_segment = 0
                elif record_type == 0x05:
                    start_address = int(data, 16)
                elif record_type == 0x01:
                    break
        return FirmwareInfo(str(path), "hex", min_address, max_address, start_address)

    @staticmethod
    def _hex_data_segments(path: Path) -> list[tuple[int, bytes]]:
        upper_linear = 0
        upper_segment = 0
        data_by_address: dict[int, int] = {}
        with path.open("r", encoding="ascii", errors="replace") as file:
            for line_number, raw_line in enumerate(file, 1):
                line = raw_line.strip()
                if not line:
                    continue
                if not line.startswith(":") or len(line) < 11:
                    raise ValueError(f"HEX 格式错误，第 {line_number} 行。")
                byte_count = int(line[1:3], 16)
                offset = int(line[3:7], 16)
                record_type = int(line[7:9], 16)
                data = line[9 : 9 + byte_count * 2]
                if record_type == 0x00:
                    base = (upper_linear << 16) + (upper_segment << 4)
                    absolute = base + offset
                    bytes_data = bytes.fromhex(data)
                    for index, value in enumerate(bytes_data):
                        data_by_address[absolute + index] = value
                elif record_type == 0x02:
                    upper_segment = int(data, 16)
                    upper_linear = 0
                elif record_type == 0x04:
                    upper_linear = int(data, 16)
                    upper_segment = 0
                elif record_type == 0x01:
                    break
        if not data_by_address:
            raise ValueError("HEX 文件没有可校验的数据记录。")
        segments: list[tuple[int, bytes]] = []
        segment_start: int | None = None
        segment_data = bytearray()
        previous_address: int | None = None
        for address in sorted(data_by_address):
            if segment_start is None:
                segment_start = address
            elif previous_address is not None and address != previous_address + 1:
                segments.append((segment_start, bytes(segment_data)))
                segment_start = address
                segment_data = bytearray()
            segment_data.append(data_by_address[address])
            previous_address = address
        if segment_start is not None:
            segments.append((segment_start, bytes(segment_data)))
        return segments

    @staticmethod
    def _required_file(value: str, label: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_file():
            raise ValueError(f"{label}不存在：{value}")
        return path

    @staticmethod
    def _required_path(value: str, label: str) -> Path:
        path = Path(value).expanduser()
        if not path.exists():
            raise ValueError(f"{label}不存在：{value}")
        return path

    @staticmethod
    def _format_command(command: list[str]) -> str:
        return " ".join(f'"{part}"' if " " in part else part for part in command)

    @staticmethod
    def _quote_commander_path(path: Path) -> str:
        return '"' + str(path).replace("\\", "/") + '"'

    def _command(self, args: list[str]) -> list[str]:
        if self._frozen:
            pyocd_exe = Path(sys.executable).with_name("pyocd.exe")
            if not pyocd_exe.is_file():
                raise FileNotFoundError(f"打包目录缺少 pyocd.exe：{pyocd_exe}")
            return [str(pyocd_exe), *args]
        return [self._python, "-m", "pyocd", *args]

    def _find_flash_algorithm_in_pack(self, pack: Path, target_key: str) -> str:
        with zipfile.ZipFile(pack) as archive:
            pdsc_names = [name for name in archive.namelist() if name.lower().endswith(".pdsc")]
            for pdsc_name in pdsc_names:
                root = ElementTree.fromstring(archive.read(pdsc_name))
                algorithm = self._extract_algorithm_from_pdsc(root, target_key)
                if algorithm:
                    return str((pack.parent / algorithm).as_posix())
        return ""

    def _find_flash_algorithm_in_dir(self, pack_dir: Path, target_key: str) -> str:
        for pdsc in pack_dir.rglob("*.pdsc"):
            root = ElementTree.parse(pdsc).getroot()
            algorithm = self._extract_algorithm_from_pdsc(root, target_key)
            if algorithm:
                candidate = pdsc.parent / algorithm
                if candidate.exists():
                    return str(candidate)
                return str(candidate)
        return ""

    def _extract_algorithm_from_pdsc(self, root: ElementTree.Element, target_key: str) -> str:
        for device in root.iter():
            tag = self._local_name(device.tag)
            if tag not in {"device", "variant"}:
                continue
            names = [device.attrib.get("Dname", ""), device.attrib.get("Dvariant", "")]
            if not any(self._normalize_target(name) == target_key for name in names):
                continue
            algorithm = self._first_algorithm(device)
            if algorithm:
                return algorithm
            parent_algorithm = self._nearest_parent_algorithm(root, device)
            if parent_algorithm:
                return parent_algorithm
        return ""

    def _first_algorithm(self, node: ElementTree.Element) -> str:
        for child in node.iter():
            if self._local_name(child.tag) == "algorithm" and child.attrib.get("name"):
                return child.attrib["name"].replace("\\", "/")
        return ""

    def _nearest_parent_algorithm(self, root: ElementTree.Element, target_node: ElementTree.Element) -> str:
        path = self._path_to_node(root, target_node)
        for node in reversed(path[:-1]):
            algorithm = self._first_algorithm(node)
            if algorithm:
                return algorithm
        return ""

    def _path_to_node(self, root: ElementTree.Element, target_node: ElementTree.Element) -> list[ElementTree.Element]:
        path: list[ElementTree.Element] = []

        def visit(node: ElementTree.Element) -> bool:
            path.append(node)
            if node is target_node:
                return True
            for child in list(node):
                if visit(child):
                    return True
            path.pop()
            return False

        visit(root)
        return path

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _normalize_target(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())
