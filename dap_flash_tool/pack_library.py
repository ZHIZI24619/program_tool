from __future__ import annotations

import json
import os
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

    @property
    def series(self) -> str:
        return self.subfamily or self.family or "未分类"

    @property
    def effective_algorithm(self) -> str:
        return self.manual_algorithm or self.algorithm


@dataclass
class PackDefinition:
    path: str
    name: str
    modified_ns: int = 0
    size: int = 0
    chips: list[ChipDefinition] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return f"{self.name}  —  {self.path}"

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
    VERSION = 1

    def __init__(self, cache_path: Path | None = None) -> None:
        self.cache_path = cache_path or self.default_cache_path()
        self.packs: list[PackDefinition] = []
        self.load()

    @staticmethod
    def default_cache_path() -> Path:
        base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
        return base / "DAPFlashTool" / "pack_library.json"

    def load(self) -> None:
        if not self.cache_path.is_file():
            return
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
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
        except (OSError, ValueError, TypeError, KeyError):
            self.packs = []

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": self.VERSION, "packs": [asdict(pack) for pack in self.packs]}
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.cache_path)

    def add(self, path_value: str) -> PackDefinition:
        path = Path(path_value).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Pack 文件或目录不存在：{path}")
        record = self._parse(path)
        previous = next(
            (pack for pack in self.packs if self._path_key(pack.path) == self._path_key(str(path))),
            None,
        )
        if previous:
            manual_algorithms = {chip.target: chip.manual_algorithm for chip in previous.chips if chip.manual_algorithm}
            for chip in record.chips:
                chip.manual_algorithm = manual_algorithms.get(chip.target, "")
        self.packs = [pack for pack in self.packs if self._path_key(pack.path) != self._path_key(str(path))]
        self.packs.append(record)
        self.packs.sort(key=lambda pack: pack.name.lower())
        self.save()
        return record

    def remove(self, path_value: str) -> None:
        key = self._path_key(path_value)
        self.packs = [pack for pack in self.packs if self._path_key(pack.path) != key]
        self.save()

    def set_manual_algorithm(self, pack_path: str, target: str, algorithm_path: str) -> None:
        for pack in self.packs:
            if self._path_key(pack.path) != self._path_key(pack_path):
                continue
            for chip in pack.chips:
                if chip.target == target:
                    chip.manual_algorithm = algorithm_path
                    self.save()
                    return

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
        inherited: dict[str, str],
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
                )
                existing = chips.get(key)
                if existing is None or (not existing.algorithm and candidate.algorithm):
                    chips[key] = candidate

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
        return os.path.normcase(os.path.abspath(value))

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
