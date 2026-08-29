# -*- coding: utf-8 -*-
"""Resource helpers shared by the PyQt UI and PyInstaller builds."""

from __future__ import annotations

import os
import sys


def asset_path(name: str) -> str:
    if getattr(sys, "_MEIPASS", None):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


def make_rounded_logo(size: int):
    from PyQt5.QtCore import QRectF, Qt
    from PyQt5.QtGui import QIcon, QPainter, QPainterPath, QPixmap

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    radius = size * 0.22
    clip.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, size, size, QIcon(asset_path("logo.ico")).pixmap(size, size))
    painter.end()
    return pm


def make_rounded_logo_icon():
    from PyQt5.QtGui import QIcon

    return QIcon(_rounded_ico_path())


def _rounded_ico_path() -> str:
    import tempfile

    from PIL import Image, ImageDraw

    ico_path = os.path.join(tempfile.gettempdir(), "DAPFlashTool_rounded.ico")
    src = Image.open(asset_path("logo.ico")).convert("RGBA")
    src = src.resize((256, 256), Image.LANCZOS)
    mask = Image.new("L", (256, 256), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, 255, 255), radius=56, fill=255)
    result = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    result = Image.composite(src, result, mask)
    result.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return ico_path
