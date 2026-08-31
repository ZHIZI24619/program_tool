from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from dap_flash_tool.pyocd_backend import FlashOptions, PyOcdBackend


def test_bin_accepts_nonstandard_flash_base(tmp_path) -> None:
    firmware = tmp_path / "app.bin"
    firmware.write_bytes(b"\x00" * 0x20)

    address = PyOcdBackend()._validate_bin_file(
        firmware,
        FlashOptions(firmware_path=str(firmware), address="0x01000000"),
    )

    assert address == "0x01000000"


def test_flash_range_is_read_from_standalone_flm(tmp_path, monkeypatch) -> None:
    algorithm = tmp_path / "flash.flm"
    algorithm.write_bytes(b"flm")
    captured = {}

    def fake_pack_flash_algo(source):
        captured["source"] = source
        return SimpleNamespace(flash_start=0x01000000, flash_size=0x40000)

    monkeypatch.setattr("pyocd.target.pack.flash_algo.PackFlashAlgo", fake_pack_flash_algo)

    assert PyOcdBackend.flash_algorithm_range(str(algorithm)) == (0x01000000, 0x40000)
    assert captured["source"] == str(algorithm)


def test_flash_range_is_read_from_flm_inside_pack(tmp_path, monkeypatch) -> None:
    pack = tmp_path / "demo.pack"
    with ZipFile(pack, "w") as archive:
        archive.writestr("Flash/demo.flm", b"packed-flm")
    captured = {}

    def fake_pack_flash_algo(source):
        captured["data"] = source.read()
        return SimpleNamespace(flash_start=0x01000000, flash_size=0x40000)

    monkeypatch.setattr("pyocd.target.pack.flash_algo.PackFlashAlgo", fake_pack_flash_algo)

    result = PyOcdBackend.flash_algorithm_range("demo.pack :: Flash/demo.flm", str(pack))

    assert result == (0x01000000, 0x40000)
    assert captured["data"] == b"packed-flm"


def test_connection_args_pass_configured_ram_to_manual_flm(tmp_path, monkeypatch) -> None:
    algorithm = tmp_path / "flash.flm"
    algorithm.write_bytes(b"flm")
    captured = {}

    def fake_script(path: Path, ram_start: int, ram_size: int) -> Path:
        captured.update(path=path, ram_start=ram_start, ram_size=ram_size)
        return tmp_path / "override.py"

    monkeypatch.setattr(PyOcdBackend, "_manual_algorithm_script", staticmethod(fake_script))

    args = PyOcdBackend()._connection_args(
        FlashOptions(
            algorithm_path=str(algorithm),
            algorithm_ram_start="0x20000100",
            algorithm_ram_size="0x800",
        )
    )

    assert captured == {"path": algorithm, "ram_start": 0x20000100, "ram_size": 0x800}
    assert args[-2:] == ["--script", str(tmp_path / "override.py")]


def test_manual_algorithm_script_uses_flm_flash_range_and_pack_ram(tmp_path, monkeypatch) -> None:
    algorithm = tmp_path / "flash.flm"
    algorithm.write_bytes(b"flm")
    monkeypatch.setattr("dap_flash_tool.pyocd_backend.tempfile.gettempdir", lambda: str(tmp_path))

    script = PyOcdBackend._manual_algorithm_script(algorithm, 0x20000100, 0x800)
    source = script.read_text(encoding="utf-8")

    compile(source, str(script), "exec")
    assert "PackFlashAlgo(FLM_PATH)" in source
    assert "start = int(pack_algo.flash_start)" in source
    assert "length = int(pack_algo.flash_size)" in source
    assert "ALGO_RAM_START = 0x20000100" in source
    assert "ALGO_RAM_SIZE = 0x800" in source
    assert "region._RAMstart = ALGO_RAM_START" in source
    assert "region._RAMsize = ALGO_RAM_SIZE" in source
    assert "processor.ap_address = APv1Address(0)" in source
    assert "pack_device._processors_ap_map = {}" in source


def test_manual_algorithm_script_uses_default_ram(tmp_path, monkeypatch) -> None:
    algorithm = tmp_path / "flash.flm"
    algorithm.write_bytes(b"flm")
    monkeypatch.setattr("dap_flash_tool.pyocd_backend.tempfile.gettempdir", lambda: str(tmp_path))

    script = PyOcdBackend._manual_algorithm_script(algorithm)
    source = script.read_text(encoding="utf-8")

    compile(source, str(script), "exec")
    assert "ALGO_RAM_START = 0x20000000" in source
    assert "ALGO_RAM_SIZE = 0x1000" in source
    assert "region._RAMstart = ALGO_RAM_START" in source


def test_erase_uses_manual_flm_flash_range(tmp_path, monkeypatch) -> None:
    algorithm = tmp_path / "flash.flm"
    algorithm.write_bytes(b"flm")
    backend = PyOcdBackend()
    captured_args = []

    monkeypatch.setattr(
        PyOcdBackend,
        "_manual_algorithm_flash_range",
        staticmethod(lambda _algorithm: (0x01000000, 0x01040000)),
    )
    monkeypatch.setattr(
        PyOcdBackend,
        "_manual_algorithm_script",
        staticmethod(lambda *_args: tmp_path / "override.py"),
    )
    monkeypatch.setattr(
        backend,
        "_run_flash_command",
        lambda args, _options, _progress=None: (captured_args.extend(args) or (0, "ok")),
    )

    code, _output = backend.erase(FlashOptions(algorithm_path=str(algorithm)))

    assert code == 0
    assert "--sector" in captured_args
    assert "0x01000000-0x01040000" in captured_args
    assert "--chip" not in captured_args
