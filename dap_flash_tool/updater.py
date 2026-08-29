# -*- coding: utf-8 -*-
"""Online updater matching the RFID_Tool release workflow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time

from PyQt5.QtCore import QObject, QTimer, QUrl, Qt
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
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


class Updater(QObject):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)

    def check(self, on_result) -> None:
        req = QNetworkRequest(QUrl(LATEST_RELEASE_URL))
        req.setTransferTimeout(15000)
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._on_check_finished(reply, on_result))

    def _on_check_finished(self, reply, on_result) -> None:
        try:
            if reply.error() != QNetworkReply.NoError:
                _log(f"检查更新失败: {reply.errorString()}")
                on_result(STATE_ERROR, None, None)
                return
            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
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
                on_result(STATE_NO_ASSET, None, None)
                return
            info = {"version": new_ver, "url": url, "sha256": sha}
            on_result(STATE_FOUND if is_newer(new_ver, __version__) else STATE_LATEST, new_ver, info)
        except Exception as exc:
            _log(f"检查更新异常: {exc}")
            on_result(STATE_ERROR, None, None)
        finally:
            reply.deleteLater()

    def download_and_launch(self, parent, info: dict) -> None:
        url = info.get("url", "")
        sha = str(info.get("sha256", "") or "")
        if not url:
            QMessageBox.warning(parent, "更新", "更新清单缺少下载地址")
            return

        fname = os.path.basename(QUrl(url).path()) or "DAPFlashTool-update.exe"
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

        req = QNetworkRequest(QUrl(url))
        req.setTransferTimeout(300000)
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        reply = self._nam.get(req)

        def on_progress(received, total):
            prog.setMaximum(max(1, total))
            prog.setValue(received)

        def on_finished():
            error = reply.error()
            payload = bytes(reply.readAll())
            error_text = reply.errorString()
            reply.deleteLater()
            if error != QNetworkReply.NoError:
                prog.close()
                msg = f"下载更新失败：{error_text}（错误码 {int(error)}）"
                _log(msg)
                QMessageBox.warning(parent, "更新", msg + "\n请检查网络后重试。")
                return
            try:
                if sha and hashlib.sha256(payload).hexdigest().lower() != sha.lower():
                    prog.close()
                    _log("sha256 校验失败")
                    QMessageBox.warning(parent, "更新", "下载文件校验失败，已中止更新")
                    return
                if len(payload) < 1024:
                    prog.close()
                    _log(f"下载内容异常：仅 {len(payload)} 字节")
                    QMessageBox.warning(parent, "更新", f"下载内容异常（仅 {len(payload)} 字节），已中止更新")
                    return
                with open(dest, "wb") as handle:
                    handle.write(payload)
            except OSError as exc:
                prog.close()
                _log(f"保存更新文件失败: {exc}")
                QMessageBox.warning(parent, "更新", f"保存更新文件失败：{exc}")
                return

            prog.setMaximum(100)
            prog.setValue(100)
            prog.setLabelText("下载完成，正在启动安装程序...")
            try:
                os.startfile(dest)
            except OSError as exc:
                prog.close()
                _log(f"启动安装程序失败: {exc}")
                QMessageBox.warning(parent, "更新", f"启动安装程序失败：{exc}\n请手动运行：\n{dest}")
                return
            QTimer.singleShot(1500, QApplication.instance().quit)
            QTimer.singleShot(5000, lambda: os._exit(0))
            _log("更新流程完成，即将退出本程序")

        reply.downloadProgress.connect(on_progress)
        reply.finished.connect(on_finished)
