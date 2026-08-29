from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree


@dataclass
class ChipDefinition:
    target: str
    vendor: str = "未知厂商"
    family: str = "未分类"
    subfamily: str = ""
    algorithm: str = ""
    manual_algorithm: str = ""
    flash_start: int | None = None
    flash_size: int | None = None

    @property
    def series(self) -> str:
        return self.subfamily or self.family or "未分类"

    @property
    def effective_algorithm(self) -> str:
        return self.manual_algorithm or self.algorithm

    @property
    def flash_end(self) -> int | None:
        if self.flash_start is None or self.flash_size is None or self.flash_size <= 0:
            return None
        return self.flash_start + self.flash_size - 1

    @property
    def flash_display(self) -> str:
        end = self.flash_end
        if self.flash_start is None or end is None:
            return "未知"
        size_k = self.flash_size / 1024
        size_text = str(int(size_k)) if size_k.is_integer() else f"{size_k:.1f}".rstrip("0").rstrip(".")
        return f"0x{self.flash_start:08X}-0x{end:08X} ({size_text}K)"


@dataclass
class PackDefinition:
    path: str
    name: str
    modified_ns: int = 0
    size: int = 0
    chips: list[ChipDefinition] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return f"{self.name}  -  {self.path}"

    def algorithm_display(self, chip: ChipDefinition) -> str:
        algorithm = chip.effective_algorithm
        if not algorithm:
            return ""
        if chip.manual_algorithm:
            return chip.manual_algorithm
        pack = Path(self.path)
        if pack.is_dir():
            return str(pack / algorithm)
        return f"{pack.name} :: {algorithm}"


class PackLibrary:
    VERSION = 3

    def __init__(self, cache_path: Path | None = None) -> None:
        self.cache_path = cache_path or self.default_cache_path()
        self.storage_path = self.default_storage_path()
        self.algorithm_storage_path = self.default_algorithm_storage_path()
        self.packs: list[PackDefinition] = []
        self.warnings: list[str] = []
        self._cache_version = 0
        self._storage_aliases: dict[str, str] = {}
        self.load()
        self.sync_from_storage()

    @staticmethod
    def default_cache_path() -> Path:
        base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
        return base / "DAPFlashTool" / "pack_library.json"

    @staticmethod
    def default_storage_path() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent / "packs"
        return Path(__file__).resolve().parents[1] / "packs"

    @staticmethod
    def default_algorithm_storage_path() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent / "algorithms"
        return Path(__file__).resolve().parents[1] / "algorithms"

    def load(self) -> None:
        if not self.cache_path.is_file():
            return
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            self._cache_version = int(data.get("version", 0) or 0)
            self.packs = [
                PackDefinition(
                    path=item["path"],
                    name=item.get("name") or Path(item["path"]).stem,
                    modified_ns=item.get("modified_ns", 0),
                    size=item.get("size", 0),
                    chips=[ChipDefinition(**chip) for chip in item.get("chips", [])],
                )
                for item in data.get("packs", [])
                if item.get("path")
            ]
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.packs = []
            self.warnings.append(f"芯片包缓存读取失败，已忽略旧缓存：{exc}")

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": self.VERSION, "packs": [asdict(pack) for pack in self.packs]}
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.cache_path)

    def add(self, path_value: str) -> PackDefinition:
        source = Path(path_value).expanduser().resolve()
        if not source.exists():
            raise ValueError(f"Pack 文件或目录不存在：{source}")

        managed = source if self._is_in_storage(source) else self._copy_to_storage(source)
        record = self._parse(managed)

        previous = next((pack for pack in self.packs if self._path_key(pack.path) == self._path_key(str(managed))), None)
        if previous:
            manual_algorithms = {chip.target: chip.manual_algorithm for chip in previous.chips if chip.manual_algorithm}
            for chip in record.chips:
                chip.manual_algorithm = manual_algorithms.get(chip.target, "")
            self._normalize_manual_algorithms(record)

        self.packs = [pack for pack in self.packs if self._path_key(pack.path) != self._path_key(str(managed))]
        self.packs.append(record)
        self.packs.sort(key=lambda pack: pack.name.lower())
        self.save()
        return record

    def remove(self, path_value: str) -> None:
        key = self._path_key(path_value)
        removed = [pack for pack in self.packs if self._path_key(pack.path) == key]
        self.packs = [pack for pack in self.packs if self._path_key(pack.path) != key]
        for pack in removed:
            self._delete_managed_copy(Path(pack.path))
        self.save()

    def sync_from_storage(self) -> None:
        cached = {self._path_key(pack.path): pack for pack in self.packs}
        loaded: list[PackDefinition] = []
        self._storage_aliases = {}

        for path in self._storage_candidates():
            key = self._path_key(str(path))
            previous_packs = [
                pack
                for cached_key, pack in cached.items()
                if cached_key == key or self._storage_aliases.get(cached_key) == key
            ]
            manual_algorithms = self._manual_algorithms_from(previous_packs)
            cached_pack = cached.get(key)
            if self._cache_version == self.VERSION and cached_pack and self._metadata_matches(path, cached_pack):
                cached_pack.path = str(path)
                self._apply_manual_algorithms(cached_pack, manual_algorithms)
                self._normalize_manual_algorithms(cached_pack)
                loaded.append(cached_pack)
                continue

            try:
                parsed = self._parse(path)
                if manual_algorithms:
                    self._apply_manual_algorithms(parsed, manual_algorithms)
                    self._normalize_manual_algorithms(parsed)
                loaded.append(parsed)
            except (OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
                self.warnings.append(f"芯片包加载失败，已跳过：{path}，原因：{exc}")

        self.packs = sorted(loaded, key=lambda pack: pack.name.lower())
        self._save_quietly()

    def set_manual_algorithm(self, pack_path: str, target: str, algorithm_path: str) -> None:
        for pack in self.packs:
            if self._path_key(pack.path) != self._path_key(pack_path):
                continue
            for chip in pack.chips:
                if chip.target == target:
                    chip.manual_algorithm = algorithm_path
                    self.save()
                    return

    def add_algorithm(self, path_value: str) -> str:
        source = Path(path_value).expanduser().resolve()
        if not source.is_file():
            raise ValueError(f"Flash 算法文件不存在：{source}")
        if source.suffix.lower() != ".flm":
            raise ValueError(f"请选择 .flm Flash 算法文件：{source}")
        managed = source if self._is_in_algorithm_storage(source) else self._copy_algorithm_to_storage(source)
        return str(managed)

    def _parse(self, path: Path) -> PackDefinition:
        roots: list[ElementTree.Element] = []
        if path.is_file():
            if not zipfile.is_zipfile(path):
                raise ValueError(f"不是有效的 CMSIS-Pack 文件：{path}")
            with zipfile.ZipFile(path) as archive:
                pdsc_names = [name for name in archive.namelist() if name.lower().endswith(".pdsc")]
                roots.extend(ElementTree.fromstring(archive.read(name)) for name in pdsc_names)
        else:
            roots.extend(ElementTree.parse(pdsc).getroot() for pdsc in path.rglob("*.pdsc"))
        if not roots:
            raise ValueError(f"Pack 中没有找到 PDSC 描述文件：{path}")

        chips: dict[str, ChipDefinition] = {}
        pack_name = path.stem
        for root in roots:
            pack_name = self._package_name(root) or pack_name
            self._walk_devices(root, chips, {})
        if not chips:
            raise ValueError(f"Pack 中没有解析到芯片：{path}")
        stat = path.stat()
        return PackDefinition(
            path=str(path),
            name=pack_name,
            modified_ns=stat.st_mtime_ns,
            size=stat.st_size if path.is_file() else 0,
            chips=sorted(chips.values(), key=lambda chip: (chip.vendor.lower(), chip.series.lower(), chip.target.lower())),
        )

    def _walk_devices(
        self,
        node: ElementTree.Element,
        chips: dict[str, ChipDefinition],
        inherited: dict[str, object],
    ) -> None:
        context = dict(inherited)
        tag = self._local_name(node.tag)
        attributes = node.attrib
        if attributes.get("Dvendor"):
            context["vendor"] = attributes["Dvendor"].split(":", 1)[0].strip()
        if attributes.get("Dfamily"):
            context["family"] = attributes["Dfamily"].strip()
        if attributes.get("DsubFamily"):
            context["subfamily"] = attributes["DsubFamily"].strip()

        direct_algorithms = [
            child.attrib.get("name", "").replace("\\", "/")
            for child in list(node)
            if self._local_name(child.tag) == "algorithm" and child.attrib.get("name")
        ]
        if direct_algorithms:
            context["algorithm"] = direct_algorithms[0]

        memory = self._flash_memory_from_node(node)
        if memory:
            context["flash_start"], context["flash_size"] = memory

        if tag in {"device", "variant"}:
            target = (attributes.get("Dvariant") or attributes.get("Dname") or "").strip()
            if target:
                key = self._target_key(target)
                candidate = ChipDefinition(
                    target=target,
                    vendor=context.get("vendor", "未知厂商"),
                    family=context.get("family", "未分类"),
                    subfamily=context.get("subfamily", ""),
                    algorithm=context.get("algorithm", ""),
                    flash_start=context.get("flash_start"),
                    flash_size=context.get("flash_size"),
                )
                existing = chips.get(key)
                if existing is None:
                    chips[key] = candidate
                else:
                    self._merge_chip_definition(existing, candidate)

        for child in list(node):
            self._walk_devices(child, chips, context)

    @classmethod
    def _package_name(cls, root: ElementTree.Element) -> str:
        for child in list(root):
            if cls._local_name(child.tag) == "name" and child.text:
                return child.text.strip()
        return ""

    @staticmethod
    def _target_key(value: str) -> str:
        return "".join(character for character in value.lower() if character.isalnum())

    @staticmethod
    def _path_key(value: str) -> str:
        if not value:
            return ""
        return os.path.normcase(os.path.abspath(value))

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def _storage_candidates(self) -> list[Path]:
        storage = self.storage_path
        if not storage.is_dir():
            return []

        candidates: list[Path] = []
        try:
            children = sorted(storage.iterdir(), key=lambda item: item.name.lower())
        except OSError as exc:
            self.warnings.append(f"芯片包目录读取失败：{storage}，原因：{exc}")
            return []

        for child in children:
            if child.is_file() and child.suffix.lower() == ".pack":
                candidates.append(child)
            elif child.is_dir() and any(child.rglob("*.pdsc")):
                candidates.append(child)
        candidates = self._normalize_storage_candidate_names(candidates)
        return self._deduplicate_storage_candidates(candidates)

    def _metadata_matches(self, path: Path, pack: PackDefinition) -> bool:
        try:
            stat = path.stat()
        except OSError:
            return False
        return stat.st_mtime_ns == pack.modified_ns and (stat.st_size if path.is_file() else 0) == pack.size

    def _copy_to_storage(self, source: Path) -> Path:
        if not source.exists():
            raise FileNotFoundError(f"Pack 文件或目录不存在：{source}")

        storage = self.storage_path
        storage.mkdir(parents=True, exist_ok=True)
        target = storage / self._managed_name(source)
        if source.is_dir():
            if target.exists():
                self._delete_managed_copy(target)
            shutil.copytree(source, target)
        else:
            if target.exists() and target.is_dir():
                self._delete_managed_copy(target)
            if not target.exists() or self._file_hash(target) != self._file_hash(source):
                shutil.copy2(source, target)
        return target

    def _copy_algorithm_to_storage(self, source: Path) -> Path:
        storage = self.algorithm_storage_path
        storage.mkdir(parents=True, exist_ok=True)
        digest = self._file_hash(source)[:12]
        target = storage / f"{source.stem}_{digest}{source.suffix.lower()}"
        if not target.is_file() or self._file_hash(target) != self._file_hash(source):
            shutil.copy2(source, target)
        return target

    def _managed_name(self, source: Path) -> str:
        digest = self._content_hash(source)[:12]
        if source.is_dir():
            return f"{self._clean_managed_stem(source.name)}_{digest}"
        return f"{self._clean_managed_stem(source.stem)}_{digest}{source.suffix.lower()}"

    def _is_in_storage(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.storage_path.resolve())
            return True
        except (OSError, ValueError):
            return False

    def _is_in_algorithm_storage(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.algorithm_storage_path.resolve())
            return True
        except (OSError, ValueError):
            return False

    def _delete_managed_copy(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            storage = self.storage_path.resolve()
            resolved.relative_to(storage)
            if resolved.is_dir():
                shutil.rmtree(resolved)
            else:
                resolved.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

    def _save_quietly(self) -> None:
        try:
            self.save()
        except OSError as exc:
            self.warnings.append(f"芯片包缓存保存失败：{exc}")

    def _normalize_manual_algorithms(self, pack: PackDefinition) -> None:
        for chip in pack.chips:
            if not chip.manual_algorithm:
                continue
            try:
                path = Path(chip.manual_algorithm).expanduser()
                if self._is_in_algorithm_storage(path):
                    if not path.is_file():
                        chip.manual_algorithm = ""
                    continue
                if path.is_file():
                    chip.manual_algorithm = str(self._copy_algorithm_to_storage(path))
                else:
                    chip.manual_algorithm = ""
            except (OSError, ValueError):
                chip.manual_algorithm = ""

    def _normalize_storage_candidate_names(self, candidates: list[Path]) -> list[Path]:
        normalized: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            target = self.storage_path / self._managed_name(path)
            key = self._path_key(str(path))
            target_key = self._path_key(str(target))
            try:
                if key == target_key:
                    normalized.append(path)
                    seen.add(key)
                    continue
                if target.exists():
                    if self._content_hash(path) == self._content_hash(target):
                        self._storage_aliases[key] = target_key
                        self._delete_managed_copy(path)
                        if target_key not in seen:
                            normalized.append(target)
                            seen.add(target_key)
                        continue
                    normalized.append(path)
                    seen.add(key)
                    continue
                path.rename(target)
                self._storage_aliases[key] = target_key
                if target_key not in seen:
                    normalized.append(target)
                    seen.add(target_key)
            except OSError as exc:
                self.warnings.append(f"芯片包缓存重命名失败，已保留旧文件：{path}，原因：{exc}")
                if key not in seen:
                    normalized.append(path)
                    seen.add(key)
        return normalized

    def _deduplicate_storage_candidates(self, candidates: list[Path]) -> list[Path]:
        content_groups: dict[str, list[Path]] = {}
        for path in candidates:
            try:
                content_groups.setdefault(self._content_hash(path), []).append(path)
            except OSError as exc:
                self.warnings.append(f"芯片包缓存读取失败，已跳过：{path}，原因：{exc}")

        unique: list[Path] = []
        for group in content_groups.values():
            if len(group) == 1:
                unique.append(group[0])
                continue

            keep = self._best_storage_candidate(group)
            unique.append(keep)
            keep_key = self._path_key(str(keep))
            for duplicate in group:
                if duplicate == keep:
                    continue
                self._storage_aliases[self._path_key(str(duplicate))] = keep_key
                self._delete_managed_copy(duplicate)
        return sorted(unique, key=lambda item: item.name.lower())

    @staticmethod
    def _best_storage_candidate(candidates: list[Path]) -> Path:
        return sorted(candidates, key=lambda item: (len(item.name), item.name.lower()))[0]

    @staticmethod
    def _clean_managed_stem(value: str) -> str:
        return re.sub(r"(?:_[0-9a-fA-F]{12})+$", "", value)

    def _content_hash(self, path: Path) -> str:
        if path.is_file():
            return self._file_hash(path)
        return self._directory_hash(path)

    def _directory_hash(self, path: Path) -> str:
        digest = hashlib.sha256()
        for child in sorted((item for item in path.rglob("*") if item.is_file()), key=lambda item: item.relative_to(path).as_posix().lower()):
            digest.update(child.relative_to(path).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(self._file_hash(child).encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _manual_algorithms_from(packs: list[PackDefinition]) -> dict[str, str]:
        manual_algorithms: dict[str, str] = {}
        for pack in packs:
            for chip in pack.chips:
                if chip.manual_algorithm and chip.target not in manual_algorithms:
                    manual_algorithms[chip.target] = chip.manual_algorithm
        return manual_algorithms

    @staticmethod
    def _apply_manual_algorithms(pack: PackDefinition, manual_algorithms: dict[str, str]) -> None:
        for chip in pack.chips:
            if chip.target in manual_algorithms and not chip.manual_algorithm:
                chip.manual_algorithm = manual_algorithms[chip.target]

    @classmethod
    def _flash_memory_from_node(cls, node: ElementTree.Element) -> tuple[int, int] | None:
        candidates: list[tuple[int, int, int]] = []
        for child in list(node):
            if cls._local_name(child.tag) != "memory":
                continue
            start = cls._parse_int(child.attrib.get("start", ""))
            size = cls._parse_int(child.attrib.get("size", ""))
            if start is None or size is None or size <= 0:
                continue

            ident = " ".join(
                str(child.attrib.get(key, ""))
                for key in ("id", "name", "Pname", "access")
            ).upper()
            score = 0
            if any(marker in ident for marker in ("FLASH", "IROM", "ROM")):
                score += 10
            if child.attrib.get("startup") == "1":
                score += 5
            if child.attrib.get("default") == "1":
                score += 3
            if "RAM" in ident or "IRAM" in ident:
                score -= 10
            if score > 0:
                candidates.append((score, start, size))

        if not candidates:
            return None
        _score, start, size = max(candidates, key=lambda item: (item[0], -item[1]))
        return start, size

    @staticmethod
    def _parse_int(value: str) -> int | None:
        text = str(value or "").strip().replace("_", "")
        if not text:
            return None
        try:
            return int(text, 0)
        except ValueError:
            match = re.fullmatch(r"#?([0-9A-Fa-f]+)H", text)
            if match:
                return int(match.group(1), 16)
        return None

    @staticmethod
    def _merge_chip_definition(existing: ChipDefinition, candidate: ChipDefinition) -> None:
        if not existing.algorithm and candidate.algorithm:
            existing.algorithm = candidate.algorithm
        if existing.flash_start is None and candidate.flash_start is not None:
            existing.flash_start = candidate.flash_start
        if existing.flash_size is None and candidate.flash_size is not None:
            existing.flash_size = candidate.flash_size

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
