from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    probe: str = ""
    target: str = ""
    pack_path: str = ""
    algorithm_path: str = ""
    firmware_path: str = ""
    address: str = ""
    frequency: str = "10MHz"
    chip_erase: bool = False
    verify: bool = True
    reset_after_download: bool = True
    dark_mode: bool = True


class AppSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self.default_path()

    @staticmethod
    def default_path() -> Path:
        base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
        return base / "DAPFlashTool" / "settings.json"

    def load(self) -> AppSettings:
        if not self.path.is_file():
            return AppSettings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = AppSettings.__dataclass_fields__.keys()
            return AppSettings(**{key: value for key, value in data.items() if key in allowed})
        except (OSError, ValueError, TypeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
