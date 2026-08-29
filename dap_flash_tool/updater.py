# -*- coding: utf-8 -*-
"""Online updater using GitHub Releases without QtNetwork."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
import urllib.parse
import urllib.request

from PyQt5.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog

from dap_flash_tool import __version__

GITHUB_REPO = "ZHIZI24619/program_tool"
SETUP_PREFIX = "DAPFlashTool-Setup-"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

STATE_ERROR = "error"
STATE_NO_ASSET = "no_asset"
STATE_LATEST = "latest"
STATE_FOUND = "found"


def _log(msg: str) -> None:
    try:
        log_path = os.path.join(tempfile.gettempdir(), "DapFlashTool_update.log")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def _parse_version(value: str) -> list[int]:
    return [int(part) for part in re.split(r"[._\-]", str(value)) if part.isdigit()] or [0]


def is_newer(remote: str, current: str) -> bool:
    return _parse_version(remote) > _parse_version(current)


def _request(url: str, timeout: int):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "DAPFlashTool",
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


class Updater(QObject):
    _check_finished = pyqtSignal(str, object, object)
    _download_progress = pyqtSignal(int, int)
    _download_finished = pyqtSignal(bool, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._check_callback = None
        self._download_dialog: QProgressDialog | None = None
        self._download_parent = None
        self._check_finished.connect(self._deliver_check_result)
        self._download_progress.connect(self._deliver_download_progress)
        self._download_finished.connect(self._deliver_download_finished)

    def check(self, on_result) -> None:
        self._check_callback = on_result
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self) -> None:
        try:
            _log(f"检查更新: {LATEST_RELEASE_URL}")
            with _request(LATEST_RELEASE_URL, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))

            new_ver = str(data.get("tag_name", "")).lstrip("vV")
            url, sha = "", ""
            for asset in data.get("assets", []) or []:
                name = asset.get("name", "")
                if name.startswith(SETUP_PREFIX) and name.lower().endswith(".exe"):
                    url = asset.get("browser_download_url", "")
                    digest = asset.get("digest", "") or ""
                    if digest.startswith("sha256:"):
                        sha = digest[len("sha256:") :]
                    break

            if not new_ver or not url:
                self._check_finished.emit(STATE_NO_ASSET, None, None)
                return

            info = {"version": new_ver, "url": url, "sha256": sha}
            state = STATE_FOUND if is_newer(new_ver, __version__) else STATE_LATEST
            self._check_finished.emit(state, new_ver, info)
        except Exception as exc:
            _log(f"检查更新异常: {exc}")
            self._check_finished.emit(STATE_ERROR, None, None)

    def _deliver_check_result(self, state, new_version, info) -> None:
        callback = self._check_callback
        self._check_callback = None
        if callback:
            callback(state, new_version, info)

    def download_and_launch(self, parent, info: dict) -> None:
        url = info.get("url", "")
        sha = str(info.get("sha256", "") or "")
        if not url:
            QMessageBox.warning(parent, "更新", "更新清单缺少下载地址")
            return

        fname = os.path.basename(urllib.parse.urlparse(url).path) or "DAPFlashTool-update.exe"
        dest = os.path.join(tempfile.gettempdir(), fname)
        _log(f"开始下载更新: {url} -> {dest}")

        prog = QProgressDialog("正在下载更新...", "", 0, 100, parent)
        prog.setCancelButton(None)
        prog.setWindowTitle("软件更新")
        prog.setWindowModality(Qt.WindowModal)
        prog.setAutoClose(False)
        prog.setAutoReset(False)
        prog.setMinimumDuration(0)
        prog.show()

        self._download_dialog = prog
        self._download_parent = parent
        threading.Thread(target=self._download_worker, args=(url, sha, dest), daemon=True).start()

    def _download_worker(self, url: str, sha: str, dest: str) -> None:
        temporary = f"{dest}.download"
        digest = hashlib.sha256()
        received = 0
        try:
            with _request(url, timeout=300) as response:
                total = int(response.headers.get("Content-Length") or "0")
                with open(temporary, "wb") as handle:
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        handle.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        self._download_progress.emit(received, total)

            if sha and digest.hexdigest().lower() != sha.lower():
                raise ValueError("下载文件校验失败，已中止更新")
            if received < 1024:
                raise ValueError(f"下载内容异常（仅 {received} 字节），已中止更新")
            os.replace(temporary, dest)
            self._download_finished.emit(True, dest)
        except Exception as exc:
            try:
                if os.path.exists(temporary):
                    os.remove(temporary)
            except OSError:
                pass
            _log(f"下载更新失败: {exc}")
            self._download_finished.emit(False, str(exc))

    def _deliver_download_progress(self, received: int, total: int) -> None:
        prog = self._download_dialog
        if prog is None:
            return
        if total > 0:
            prog.setRange(0, total)
            prog.setValue(min(received, total))
        else:
            prog.setRange(0, 0)

    def _deliver_download_finished(self, ok: bool, payload) -> None:
        prog = self._download_dialog
        parent = self._download_parent
        self._download_dialog = None
        self._download_parent = None
        if prog is None:
            return

        if not ok:
            prog.close()
            QMessageBox.warning(parent, "更新", f"下载更新失败：{payload}\n请检查网络后重试。")
            return

        dest = str(payload)
        prog.setRange(0, 100)
        prog.setValue(100)
        prog.setLabelText("下载完成，正在启动安装程序...")
        try:
            os.startfile(dest)
        except OSError as exc:
            prog.close()
            _log(f"启动安装程序失败: {exc}")
            QMessageBox.warning(parent, "更新", f"启动安装程序失败：{exc}\n请手动运行：\n{dest}")
            return

        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(1500, app.quit)
        QTimer.singleShot(5000, lambda: os._exit(0))
        _log("更新流程完成，即将退出本程序")
