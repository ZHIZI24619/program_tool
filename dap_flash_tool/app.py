from __future__ import annotations

import ctypes
import math
import os
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
    QObject,
)
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .app_settings import AppSettings, AppSettingsStore
from .pack_library import ChipDefinition, PackDefinition, PackLibrary
from .pyocd_backend import FlashOptions, PyOcdBackend
from .resources import make_rounded_logo, make_rounded_logo_icon

if sys.platform.startswith("win"):
    import ctypes.wintypes

    WM_NCHITTEST = 0x0084
    WM_GETMINMAXINFO = 0x0024
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_DONOTROUND = 1
    DWMWCP_ROUND = 2
    HTCLIENT = 1
    HTCAPTION = 2
    HTLEFT = 10
    HTRIGHT = 11
    HTTOP = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOM = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17
    RESIZE_MARGIN = 6

    class _WinPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class _MinMaxInfo(ctypes.Structure):
        _fields_ = [
            ("ptReserved", _WinPoint),
            ("ptMaxSize", _WinPoint),
            ("ptMaxPosition", _WinPoint),
            ("ptMinTrackSize", _WinPoint),
            ("ptMaxTrackSize", _WinPoint),
        ]


class _Signals(QObject):
    finished = pyqtSignal(str, int, str, object, object)
    failed = pyqtSignal(str, str)


class _ThemeRevealOverlay(QWidget):
    def __init__(self, window: QWidget, old_pix: QPixmap, new_pix: QPixmap, center: QPoint) -> None:
        super().__init__(window)
        self._old = old_pix
        self._new = new_pix
        self._center = center
        self._progress = 0.0
        self._max_r = math.hypot(max(center.x(), window.width() - center.x()), max(center.y(), window.height() - center.y()))
        self.setGeometry(0, 0, window.width(), window.height())
        self.raise_()
        self.show()

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(600)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(self._on_progress)
        self._anim.finished.connect(self._on_finished)

    def start_animation(self) -> None:
        self._anim.start()

    def _on_progress(self, value) -> None:
        self._progress = float(value)
        self.update()

    def _on_finished(self) -> None:
        self.hide()
        self.deleteLater()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, self._old)
        path = QPainterPath()
        radius = self._progress * self._max_r
        path.addEllipse(QPointF(self._center), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, self._new)


class _VisibleCheckBox(QCheckBox):
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.isChecked():
            return

        option = QStyleOptionButton()
        self.initStyleOption(option)
        indicator = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self)
        if not indicator.isValid():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#ffffff" if self.isEnabled() else "#a0a7b2"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        x = indicator.x()
        y = indicator.y()
        w = indicator.width()
        h = indicator.height()
        path = QPainterPath()
        path.moveTo(x + w * 0.25, y + h * 0.55)
        path.lineTo(x + w * 0.43, y + h * 0.72)
        path.lineTo(x + w * 0.76, y + h * 0.30)
        painter.drawPath(path)


class DapFlashApp(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DAP Flash Tool")
        self.setMinimumSize(880, 580)
        self.resize(980, 640)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setObjectName("mainWindow")
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)

        self.backend = PyOcdBackend()
        self.pack_library = PackLibrary()
        self.settings_store = AppSettingsStore()
        self.saved_settings = self.settings_store.load()
        self.selected_chip: tuple[PackDefinition, ChipDefinition] | None = None
        self.pack_targets: list[str] = []
        self.action_buttons: list[QPushButton] = []
        self._dark_mode = bool(self.saved_settings.dark_mode)
        self._native_corners_supported: bool | None = None

        self._signals = _Signals(self)
        self._signals.finished.connect(self._finish_command)
        self._signals.failed.connect(self._fail_command)

        self._build_ui()
        self._load_pack_library()
        self._restore_settings()
        self._restore_last_chip()
        self._apply_theme()

        QTimer.singleShot(0, self._deferred_center)
        QTimer.singleShot(800, self.refresh_probes)
        QTimer.singleShot(2000, self._check_update_on_startup)

    # ------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_title_bar()
        root.addWidget(self.title_bar)

        self._build_toolbar()
        root.addWidget(self.toolbar)

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(8, 8, 8, 8)
        body_lay.setSpacing(8)
        body_lay.addWidget(self._build_config_panel(), 0)
        body_lay.addWidget(self._build_log_panel(), 1)
        root.addWidget(body, 1)

        self.status_bar = QWidget()
        self.status_bar.setObjectName("statusBar")
        self.status_bar.setAttribute(Qt.WA_StyledBackground, True)
        status_lay = QHBoxLayout(self.status_bar)
        status_lay.setContentsMargins(8, 3, 8, 3)
        status_lay.setSpacing(8)
        self.status_label = QLabel("就绪")
        status_lay.addWidget(self.status_label)
        status_lay.addStretch(1)
        root.addWidget(self.status_bar)

    def _build_title_bar(self) -> None:
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(34)
        bar.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 0, 6, 0)
        lay.setSpacing(2)

        self.title_logo = QLabel()
        self.title_logo.setFixedSize(20, 20)
        self.title_logo.setPixmap(make_rounded_logo(20))
        self.title_logo.setToolTip("DAP Flash Tool")
        self.title_label = QLabel("DAP Flash Tool")
        self.title_label.setObjectName("titleLabel")
        lay.addWidget(self.title_logo)
        lay.addWidget(self.title_label)
        lay.addStretch(1)

        self._title_buttons: list[QToolButton] = []
        self._title_bar_layout = lay
        self.btn_title_theme = self._make_title_button("", self._toggle_theme)
        self.btn_title_theme.setFixedSize(44, 26)
        self.btn_title_theme.setIconSize(QSize(18, 18))
        self.btn_title_theme.setToolTip("切换 白天 / 夜间 模式")
        self.btn_title_min = self._make_title_button("-", self.showMinimized)
        self.btn_title_max = self._make_title_button("□", self._toggle_maximize)
        self.btn_title_close = self._make_title_button("✕", self.close, close=True)
        self.title_bar = bar

    def _make_title_button(self, text: str, slot, close: bool = False) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setObjectName("titleBtnClose" if close else "titleBtn")
        btn.setFixedSize(40, 26)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(slot)
        self._title_bar_layout.addWidget(btn)
        self._title_buttons.append(btn)
        return btn

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.toolbar = toolbar

        toolbar.addWidget(QLabel("调试器 "))
        self.probe_combo = QComboBox()
        self.probe_combo.setEditable(False)
        self.probe_combo.setMinimumWidth(260)
        toolbar.addWidget(self.probe_combo)

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setToolTip("刷新 CMSIS-DAP 探针列表")
        self.btn_refresh.clicked.connect(self.refresh_probes)
        toolbar.addWidget(self.btn_refresh)

        self.btn_detect = QPushButton("检测连接")
        self.btn_detect.clicked.connect(self.detect_chip)
        toolbar.addWidget(self.btn_detect)

        self.btn_download = QPushButton("下载")
        self.btn_download.setObjectName("btnPrimary")
        self.btn_download.clicked.connect(self.download_firmware)
        toolbar.addWidget(self.btn_download)
        self.action_buttons.extend([self.btn_refresh, self.btn_detect, self.btn_download])

        toolbar.addSeparator()
        self.btn_add_pack = QPushButton("添加芯片包")
        self.btn_add_pack.clicked.connect(self.select_pack)
        toolbar.addWidget(self.btn_add_pack)
        self.btn_pack_manager = QPushButton("芯片管理")
        self.btn_pack_manager.clicked.connect(self.open_pack_manager)
        toolbar.addWidget(self.btn_pack_manager)

        self._update_sep_a = toolbar.addSeparator()
        self.btn_check_update = QPushButton("更新")
        self.btn_check_update.setObjectName("btnUpdate")
        self.btn_check_update.clicked.connect(self._start_update)
        self.btn_check_update.setVisible(False)
        toolbar.addWidget(self.btn_check_update)
        self._update_sep_b = toolbar.addSeparator()
        self._update_sep_a.setVisible(False)
        self._update_sep_b.setVisible(False)

        self.status_badge = QLabel("就绪")
        self.status_badge.setObjectName("badgeReady")
        toolbar.addWidget(self.status_badge)

    def _build_config_panel(self) -> QWidget:
        page = QWidget()
        page.setFixedWidth(360)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        target = QGroupBox("连接与目标")
        target_lay = QGridLayout(target)
        target_lay.setContentsMargins(10, 10, 10, 10)
        target_lay.setHorizontalSpacing(8)
        target_lay.setVerticalSpacing(6)
        self.target_edit = QLineEdit()
        self.target_edit.setReadOnly(True)
        self.btn_select_chip = QPushButton("选择芯片")
        self.btn_select_chip.clicked.connect(self.open_chip_selector)
        target_lay.addWidget(QLabel("目标芯片："), 0, 0, Qt.AlignRight)
        target_lay.addWidget(self.target_edit, 0, 1)
        target_lay.addWidget(self.btn_select_chip, 0, 2)
        self.frequency_combo = QComboBox()
        self.frequency_combo.addItems(["1MHz", "2MHz", "4MHz", "8MHz", "10MHz", "12MHz", "16MHz", "24MHz"])
        self.frequency_combo.setEditable(True)
        target_lay.addWidget(QLabel("DAP 频率："), 1, 0, Qt.AlignRight)
        target_lay.addWidget(self.frequency_combo, 1, 1, 1, 2)
        self.address_edit = QLineEdit()
        target_lay.addWidget(QLabel("起始地址："), 2, 0, Qt.AlignRight)
        target_lay.addWidget(self.address_edit, 2, 1, 1, 2)
        lay.addWidget(target)

        files = QGroupBox("算法与固件")
        files_lay = QGridLayout(files)
        files_lay.setContentsMargins(10, 10, 10, 10)
        files_lay.setHorizontalSpacing(8)
        files_lay.setVerticalSpacing(6)
        self.algorithm_edit = QLineEdit()
        btn_algorithm = QPushButton("浏览")
        btn_algorithm.clicked.connect(self.select_algorithm)
        files_lay.addWidget(QLabel("Flash 算法："), 0, 0, Qt.AlignRight)
        files_lay.addWidget(self.algorithm_edit, 0, 1)
        files_lay.addWidget(btn_algorithm, 0, 2)
        self.firmware_edit = QLineEdit()
        btn_firmware = QPushButton("浏览")
        btn_firmware.clicked.connect(self.select_firmware)
        files_lay.addWidget(QLabel("固件文件："), 1, 0, Qt.AlignRight)
        files_lay.addWidget(self.firmware_edit, 1, 1)
        files_lay.addWidget(btn_firmware, 1, 2)
        lay.addWidget(files)

        options = QGroupBox("下载选项")
        opt_lay = QVBoxLayout(options)
        opt_lay.setContentsMargins(10, 10, 10, 10)
        opt_lay.setSpacing(6)
        self.chip_erase_check = _VisibleCheckBox("下载前全片擦除")
        self.verify_check = _VisibleCheckBox("下载后检验")
        self.reset_check = _VisibleCheckBox("完成后复位运行")
        opt_lay.addWidget(self.chip_erase_check)
        opt_lay.addWidget(self.verify_check)
        opt_lay.addWidget(self.reset_check)
        lay.addWidget(options)

        actions = QWidget()
        actions_lay = QHBoxLayout(actions)
        actions_lay.setContentsMargins(0, 0, 0, 0)
        actions_lay.setSpacing(8)
        self.btn_erase = QPushButton("擦除")
        self.btn_erase.clicked.connect(self.erase_chip)
        self.btn_verify = QPushButton("校验")
        self.btn_verify.clicked.connect(self.verify_firmware)
        self.btn_reset = QPushButton("复位运行")
        self.btn_reset.clicked.connect(self.reset_run)
        actions_lay.addWidget(self.btn_erase)
        actions_lay.addWidget(self.btn_verify)
        actions_lay.addWidget(self.btn_reset)
        self.action_buttons.extend([self.btn_erase, self.btn_verify, self.btn_reset])
        lay.addWidget(actions)

        hint = QLabel("HEX/ELF/AXF 会自动读取地址范围；BIN 需要填写起始地址。芯片包只在添加时解析，启动时直接读取缓存。")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addStretch(1)
        return page

    def _build_log_panel(self) -> QWidget:
        group = QGroupBox("执行日志")
        lay = QVBoxLayout(group)
        lay.setContentsMargins(10, 10, 10, 10)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(200000)
        lay.addWidget(self.log_view)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(self._clear_log)
        bottom.addWidget(btn_clear)
        lay.addLayout(bottom)
        return group

    # ------------------------------------------------------------- settings
    def _restore_settings(self) -> None:
        s = self.saved_settings
        self.target_edit.setText(s.target)
        self.frequency_combo.setCurrentText(s.frequency or "10MHz")
        self.address_edit.setText(s.address)
        self.algorithm_edit.setText(s.algorithm_path)
        self.firmware_edit.setText(s.firmware_path)
        self.chip_erase_check.setChecked(s.chip_erase)
        self.verify_check.setChecked(s.verify)
        self.reset_check.setChecked(s.reset_after_download)

    def _current_settings(self) -> AppSettings:
        return AppSettings(
            probe=self.probe_combo.currentText().strip(),
            target=self.target_edit.text().strip(),
            pack_path=self._selected_pack_path(),
            algorithm_path=self.algorithm_edit.text().strip(),
            firmware_path=self.firmware_edit.text().strip(),
            address=self.address_edit.text().strip(),
            frequency=self.frequency_combo.currentText().strip(),
            chip_erase=self.chip_erase_check.isChecked(),
            verify=self.verify_check.isChecked(),
            reset_after_download=self.reset_check.isChecked(),
            dark_mode=self._dark_mode,
        )

    def _save_settings(self) -> None:
        try:
            self.settings_store.save(self._current_settings())
        except OSError as exc:
            QMessageBox.warning(self, "保存设置", f"无法保存上次使用记录：{exc}")

    def closeEvent(self, event) -> None:
        self._save_settings()
        super().closeEvent(event)

    # ------------------------------------------------------------- actions
    def refresh_probes(self) -> None:
        self._run_command("刷新探针", self._list_probes, self._update_probe_list)

    def _list_probes(self) -> tuple[int, str]:
        code, output = self.backend.list_probes()
        if code != 0 and self.backend.has_no_probe(output):
            return 0, f"{output}\n\n未发现 DAP 设备，请插入调试器后点击刷新。"
        return code, output

    def detect_chip(self) -> None:
        self._run_command("检测连接", lambda: self._target_command(self.backend.detect_chip))

    def erase_chip(self) -> None:
        self._run_command("擦除", lambda: self.backend.erase(self._collect_options()))

    def download_firmware(self) -> None:
        options = self._collect_options()
        if options.chip_erase:
            self._run_command(
                "擦除",
                lambda: self.backend.erase(options),
                lambda _output: self._start_download_stage(options),
                start_message="开始擦除",
                success_message="擦除完成",
            )
        else:
            self._start_download_stage(options)

    def verify_firmware(self) -> None:
        self._run_command("校验", lambda: self.backend.verify(self._collect_options()))

    def reset_run(self) -> None:
        self._run_command("复位运行", lambda: self.backend.reset_run(self._collect_options()))

    def _after_download(self, options: FlashOptions, _output: str) -> None:
        if options.verify_after_download:
            self._run_command(
                "检验",
                lambda: self.backend.verify(options),
                lambda _verify_output: self._after_verify(options),
                start_message="开始检验",
                success_message="检验完成",
            )
        elif options.reset_after_download:
            self._start_reset_stage(options)

    def _after_verify(self, options: FlashOptions) -> None:
        if options.reset_after_download:
            self._start_reset_stage(options)

    def _start_download_stage(self, options: FlashOptions) -> None:
        self._run_command(
            "下载",
            lambda: self.backend.download(options),
            lambda output: self._after_download(options, output),
            start_message="开始下载",
            success_message="下载完成",
        )

    def _start_reset_stage(self, options: FlashOptions) -> None:
        self._run_command(
            "复位运行",
            lambda: self.backend.reset_run(options),
            start_message="开始复位运行",
            success_message="复位运行完成",
        )

    def _target_command(self, command: Callable[[FlashOptions], tuple[int, str]]) -> tuple[int, str]:
        options = self._collect_options()
        code, output = command(options)
        if self.backend.has_no_target(output):
            return 0, "未连接目标芯片，请确认目标板已上电、SWD 接线正确，并尝试降低 DAP 频率后重试。"
        return code, output

    def _collect_options(self) -> FlashOptions:
        return FlashOptions(
            probe_uid=self.backend.normalize_probe_uid(self.probe_combo.currentText().strip()),
            target=self.target_edit.text().strip(),
            pack_path=self._selected_pack_path(),
            algorithm_path=self.algorithm_edit.text().strip(),
            firmware_path=self.firmware_edit.text().strip(),
            address=self.address_edit.text().strip(),
            frequency=self.frequency_combo.currentText().strip(),
            chip_erase=self.chip_erase_check.isChecked(),
            verify_after_download=self.verify_check.isChecked(),
            reset_after_download=self.reset_check.isChecked(),
        )

    def _run_command(
        self,
        name: str,
        task: Callable[[], tuple[int, str]],
        success_handler: Callable[[str], None] | None = None,
        start_message: str | None = None,
        success_message: str | None = None,
    ) -> None:
        self._set_busy(True, name)
        self._append_log(f"[{self._now()}] {start_message or f'开始：{name}'}")

        def execute() -> None:
            try:
                code, output = task()
                self._signals.finished.emit(name, code, output, success_handler, success_message)
            except Exception as exc:
                self._signals.failed.emit(name, str(exc))

        threading.Thread(target=execute, daemon=True).start()

    def _finish_command(self, name: str, code: int, output: str, success_handler, success_message) -> None:
        if output.strip():
            self._append_log(output)
        if code == 0:
            self._append_log(f"[{self._now()}] {success_message or f'完成：{name}'}")
            self._set_busy(False, status="完成")
            if success_handler:
                success_handler(output)
        else:
            self._append_log(f"[{self._now()}] 失败：{name}，退出码 {code}")
            self._set_busy(False, status="失败")

    def _fail_command(self, name: str, message: str) -> None:
        self._append_log(f"[{self._now()}] 异常：{name}\n{message}")
        self._set_busy(False, status="异常")
        QMessageBox.warning(self, name, message)

    # ------------------------------------------------------------- packs
    def select_pack(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "添加 CMSIS-Pack（可多选）", "", "CMSIS-Pack (*.pack);;所有文件 (*)")
        if not paths:
            return
        self._set_busy(True, "解析 Pack")
        QApplication.processEvents()
        added = 0
        errors: list[str] = []
        for path in paths:
            try:
                record = self.pack_library.add(path)
                added += 1
                self._append_log(f"已复制并缓存 Pack：{record.name}，{len(record.chips)} 个芯片。\n{record.path}")
            except Exception as exc:
                errors.append(f"{path}\n{exc}")
        self._load_pack_library()
        self._set_busy(False, status="完成" if added else "失败")
        if errors:
            QMessageBox.warning(self, "添加 Pack", "以下 Pack 添加失败：\n\n" + "\n\n".join(errors))

    def open_pack_manager(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("芯片包管理")
        dialog.resize(760, 420)
        lay = QVBoxLayout(dialog)
        table = self._make_table(["芯片包", "芯片数", "文件路径"])
        lay.addWidget(table)

        def populate() -> None:
            table.setRowCount(len(self.pack_library.packs))
            for row, pack in enumerate(self.pack_library.packs):
                table.setItem(row, 0, self._item(pack.name, pack))
                table.setItem(row, 1, self._item(str(len(pack.chips))))
                table.setItem(row, 2, self._item(pack.path))
            table.resizeColumnsToContents()
            table.horizontalHeader().setStretchLastSection(True)

        def add_pack() -> None:
            self.select_pack()
            populate()

        def remove_pack() -> None:
            row = table.currentRow()
            if row < 0:
                return
            pack = table.item(row, 0).data(Qt.UserRole)
            if not QMessageBox.question(dialog, "移除 Pack", f"从缓存库移除 {pack.name}？\n不会删除原始 Pack 文件。") == QMessageBox.Yes:
                return
            self.pack_library.remove(pack.path)
            if self.selected_chip and self.selected_chip[0].path == pack.path:
                self.selected_chip = None
                self.target_edit.clear()
                self.algorithm_edit.clear()
            self._load_pack_library()
            self._append_log(f"已从缓存库移除 Pack：{pack.name}。")
            populate()

        buttons = QHBoxLayout()
        btn_add = QPushButton("添加芯片包")
        btn_add.setObjectName("btnPrimary")
        btn_add.clicked.connect(add_pack)
        btn_remove = QPushButton("移除")
        btn_remove.setObjectName("btnDanger")
        btn_remove.clicked.connect(remove_pack)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dialog.accept)
        buttons.addWidget(btn_add)
        buttons.addWidget(btn_remove)
        buttons.addStretch(1)
        buttons.addWidget(btn_close)
        lay.addLayout(buttons)
        populate()
        dialog.exec_()

    def open_chip_selector(self) -> None:
        if not self.pack_library.packs:
            QMessageBox.information(self, "选择芯片", "尚未添加芯片包，请先添加。")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("选择目标芯片")
        dialog.resize(900, 560)
        lay = QVBoxLayout(dialog)

        filters = QHBoxLayout()
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("搜索芯片、厂商、系列或芯片包")
        vendor_combo = QComboBox()
        family_combo = QComboBox()
        filters.addWidget(search_edit, 1)
        filters.addWidget(vendor_combo)
        filters.addWidget(family_combo)
        lay.addLayout(filters)

        table = self._make_table(["芯片型号", "厂商", "系列", "芯片包"])
        self._configure_chip_table(table)
        lay.addWidget(table, 1)
        entries = [(pack, chip) for pack in self.pack_library.packs for chip in pack.chips]
        visible: list[tuple[PackDefinition, ChipDefinition]] = []

        def populate(update_families: bool = False) -> None:
            vendors = sorted({chip.vendor for _pack, chip in entries}, key=str.lower)
            current_vendor = vendor_combo.currentText() or "全部厂商"
            self._replace_combo_items(vendor_combo, ["全部厂商", *vendors], current_vendor)
            vendor = vendor_combo.currentText()
            by_vendor = entries if vendor == "全部厂商" else [item for item in entries if item[1].vendor == vendor]
            families = sorted({chip.series for _pack, chip in by_vendor}, key=str.lower)
            current_family = "全部系列" if update_families else (family_combo.currentText() or "全部系列")
            self._replace_combo_items(family_combo, ["全部系列", *families], current_family)
            family = family_combo.currentText()
            matches = by_vendor if family == "全部系列" else [item for item in by_vendor if item[1].series == family]
            query = search_edit.text().strip().lower()
            if query:
                matches = [
                    item
                    for item in matches
                    if query in " ".join((item[1].target, item[1].vendor, item[1].series, item[0].name)).lower()
                ]
            visible[:] = sorted(matches, key=lambda value: value[1].target.lower())
            table.setRowCount(len(visible))
            for row, (pack, chip) in enumerate(visible):
                table.setItem(row, 0, self._item(chip.target, (pack, chip)))
                table.setItem(row, 1, self._item(chip.vendor))
                table.setItem(row, 2, self._item(chip.series))
                table.setItem(row, 3, self._item(pack.name))
            self._configure_chip_table(table)

        def confirm() -> None:
            row = table.currentRow()
            if row < 0:
                QMessageBox.information(dialog, "选择芯片", "请先选择一个芯片。")
                return
            pack, chip = table.item(row, 0).data(Qt.UserRole)
            self._select_chip(pack, chip)
            dialog.accept()

        vendor_combo.currentTextChanged.connect(lambda _text: populate(True))
        family_combo.currentTextChanged.connect(lambda _text: populate(False))
        search_edit.textChanged.connect(lambda _text: populate(False))
        table.doubleClicked.connect(lambda _index: confirm())

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(dialog.reject)
        btn_ok = QPushButton("确认选择")
        btn_ok.setObjectName("btnPrimary")
        btn_ok.clicked.connect(confirm)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        lay.addLayout(buttons)
        populate()
        dialog.exec_()

    def _load_pack_library(self) -> None:
        self.pack_targets = sorted({chip.target for pack in self.pack_library.packs for chip in pack.chips}, key=str.lower)

    def _restore_last_chip(self) -> None:
        target = self.saved_settings.target
        pack_path = self.saved_settings.pack_path
        if not target:
            return
        path_key = os.path.normcase(os.path.abspath(pack_path)) if pack_path else ""
        for pack in self.pack_library.packs:
            if path_key and os.path.normcase(os.path.abspath(pack.path)) != path_key:
                continue
            chip = next((item for item in pack.chips if item.target == target), None)
            if chip:
                self._select_chip(pack, chip, log=False)
                return

    def _select_chip(self, pack: PackDefinition, chip: ChipDefinition, log: bool = True) -> None:
        self.selected_chip = (pack, chip)
        self.target_edit.setText(chip.target)
        self.auto_detect_flash_algorithm()
        if log:
            self._append_log(f"已选择芯片：{chip.vendor} / {chip.series} / {chip.target}（{pack.name}）")

    def _selected_pack_path(self) -> str:
        if self.selected_chip:
            return self.selected_chip[0].path
        return self.saved_settings.pack_path if self.target_edit.text().strip() == self.saved_settings.target else ""

    def select_algorithm(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "选择 Flash 算法", "", "Flash Algorithm (*.flm *.FLM);;所有文件 (*)")
        if not selected:
            return
        self.algorithm_edit.setText(selected)
        if self.selected_chip:
            pack, chip = self.selected_chip
            chip.manual_algorithm = selected
            self.pack_library.set_manual_algorithm(pack.path, chip.target, selected)
            self._append_log(f"已为 {chip.target} 保存手动算法：{selected}")
        else:
            self._append_log("已选择算法文件；选择缓存库中的芯片后才能保存芯片映射。")

    def select_firmware(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "选择固件", "", "Firmware (*.hex *.bin *.elf *.axf);;所有文件 (*)")
        if not selected:
            return
        self.firmware_edit.setText(selected)
        if Path(selected).suffix.lower() in {".hex", ".elf", ".axf"}:
            self.address_edit.clear()
        self.analyze_firmware()

    def analyze_firmware(self) -> None:
        try:
            info = self.backend.analyze_firmware(self.firmware_edit.text().strip())
        except Exception as exc:
            self._append_log(f"固件分析失败：{exc}")
            return
        self._append_log(self.backend.format_firmware_info(info))
        if info.min_address is not None and not self.address_edit.text().strip():
            self.address_edit.setText(f"0x{info.min_address:08X}")

    def auto_detect_flash_algorithm(self) -> None:
        if not self.selected_chip:
            return
        pack, chip = self.selected_chip
        algorithm = pack.algorithm_display(chip)
        if algorithm:
            self.algorithm_edit.setText(algorithm)
            self._append_log(f"自动识别 Flash 算法：{algorithm}")
        else:
            self.algorithm_edit.clear()
            self._append_log(f"{chip.target} 没有匹配到 Flash 算法，请手动添加 FLM 文件。")

    # ------------------------------------------------------------- updater
    def _check_update_on_startup(self) -> None:
        from .updater import STATE_FOUND, Updater

        updater = Updater(self)
        self._updater = updater

        def on_result(state, new_version, info) -> None:
            if state == STATE_FOUND:
                self._update_info = info
                self.btn_check_update.setText(f"更新 v{new_version}")
                self.btn_check_update.setVisible(True)
                self._update_sep_a.setVisible(True)
                self._update_sep_b.setVisible(True)

        updater.check(on_result)

    def _start_update(self) -> None:
        from .updater import Updater

        info = getattr(self, "_update_info", None)
        if not info:
            self.btn_check_update.setVisible(False)
            self._update_sep_a.setVisible(False)
            self._update_sep_b.setVisible(False)
            return
        new_version = info.get("version")
        ret = QMessageBox.question(
            self,
            "发现新版本",
            f"发现新版本 v{new_version}（当前 v{__version__}）。\n是否下载并安装？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ret == QMessageBox.Yes:
            updater = Updater(self)
            self._updater = updater
            updater.download_and_launch(self, info)

    # ------------------------------------------------------------- theme/window
    def _toggle_theme(self) -> None:
        center = self.btn_title_theme.mapTo(self, QPoint(self.btn_title_theme.width() // 2, self.btn_title_theme.height() // 2))
        old_pix = self.grab()
        self._dark_mode = not self._dark_mode
        self._apply_theme()
        new_pix = self.grab()
        overlay = _ThemeRevealOverlay(self, old_pix, new_pix, center)
        overlay.start_animation()

    def _apply_theme(self) -> None:
        from .theme import LIGHT_QSS, QSS

        app = QApplication.instance()
        app.setStyleSheet(QSS if self._dark_mode else LIGHT_QSS)
        if self._dark_mode:
            self.btn_title_theme.setIcon(QIcon(self._make_sun_icon(QColor("#ffd35c"))))
        else:
            self.btn_title_theme.setIcon(QIcon(self._make_moon_icon(QColor("#2b3038"))))
        for widget in QApplication.allWidgets():
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _make_moon_icon(self, color: QColor, size: int = 24) -> QPixmap:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        cx, cy = size / 2.0, size / 2.0
        radius = size * 0.38
        moon = QPainterPath()
        moon.addEllipse(QPointF(cx, cy), radius, radius)
        inner = QPainterPath()
        inner.addEllipse(QPointF(cx - radius * 0.55, cy - radius * 0.12), radius, radius)
        painter.drawPath(moon.subtracted(inner))
        painter.end()
        return pm

    def _make_sun_icon(self, color: QColor, size: int = 24) -> QPixmap:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = size / 2.0, size / 2.0
        painter.setPen(QPen(color, size * 0.09, Qt.SolidLine, Qt.RoundCap))
        for index in range(8):
            angle = math.radians(index * 45)
            x1 = cx + math.cos(angle) * size * 0.26
            y1 = cy + math.sin(angle) * size * 0.26
            x2 = cx + math.cos(angle) * size * 0.40
            y2 = cy + math.sin(angle) * size * 0.40
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(cx, cy), size * 0.21, size * 0.21)
        painter.end()
        return pm

    def nativeEvent(self, eventType, message):
        if not sys.platform.startswith("win"):
            return super().nativeEvent(eventType, message)
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCHITTEST:
                return True, self._nchittest(msg)
            if msg.message == WM_GETMINMAXINFO:
                self._getminmaxinfo(msg)
                return True, 0
        return super().nativeEvent(eventType, message)

    def _nchittest(self, msg):
        pos = self.mapFromGlobal(QPoint(msg.pt.x, msg.pt.y))
        margin = RESIZE_MARGIN
        width, height = self.width(), self.height()
        if not self.isMaximized():
            left = pos.x() <= margin
            right = pos.x() >= width - margin
            top = pos.y() <= margin
            bottom = pos.y() >= height - margin
            if top and left:
                return HTTOPLEFT
            if top and right:
                return HTTOPRIGHT
            if bottom and left:
                return HTBOTTOMLEFT
            if bottom and right:
                return HTBOTTOMRIGHT
            if left:
                return HTLEFT
            if right:
                return HTRIGHT
            if top:
                return HTTOP
            if bottom:
                return HTBOTTOM
        title_rect = self.title_bar.geometry()
        if title_rect.contains(pos):
            for btn in self._title_buttons:
                rect = QRect(title_rect.topLeft() + btn.geometry().topLeft(), btn.size())
                if rect.contains(pos):
                    return HTCLIENT
            return HTCAPTION
        return HTCLIENT

    def _getminmaxinfo(self, msg) -> None:
        mmi = ctypes.cast(msg.lParam, ctypes.POINTER(_MinMaxInfo)).contents
        work = QApplication.primaryScreen().availableGeometry()
        mmi.ptMaxSize.x = work.width()
        mmi.ptMaxSize.y = work.height()
        mmi.ptMaxPosition.x = work.x()
        mmi.ptMaxPosition.y = work.y()
        mmi.ptMaxTrackSize.x = work.width()
        mmi.ptMaxTrackSize.y = work.height()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.WindowStateChange:
            maximized = self.isMaximized()
            self.btn_title_max.setText("❐" if maximized else "□")
            value = "true" if maximized else "false"
            for widget in (self, self.title_bar, self.status_bar):
                widget.setProperty("winMaximized", value)
                widget.style().unpolish(widget)
                widget.style().polish(widget)
            QTimer.singleShot(0, self._apply_window_corners)
        super().changeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_window_corners)
        QTimer.singleShot(0, self._deferred_center)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._native_corners_supported is False:
            self._apply_rounded_mask()

    def _apply_window_corners(self) -> None:
        if not sys.platform.startswith("win"):
            return
        preference = ctypes.c_int(DWMWCP_DONOTROUND if self.isMaximized() else DWMWCP_ROUND)
        try:
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()),
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(preference),
                ctypes.sizeof(preference),
            )
        except (AttributeError, OSError):
            result = -1
        self._native_corners_supported = result == 0
        if self._native_corners_supported:
            self.clearMask()
        else:
            self._apply_rounded_mask()

    def _apply_rounded_mask(self) -> None:
        if self.isMaximized():
            self.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10.0, 10.0)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _deferred_center(self) -> None:
        if not self.isVisible() or self.isMaximized():
            return
        frame = self.frameGeometry()
        screen = QApplication.primaryScreen().availableGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())

    # ------------------------------------------------------------- helpers
    def _update_probe_list(self, output: str) -> None:
        probes = self.backend.extract_probe_ids(output)
        current_uid = self.backend.normalize_probe_uid(self.probe_combo.currentText().strip())
        saved_uid = self.backend.normalize_probe_uid(self.saved_settings.probe.strip())
        preferred_uid = current_uid or saved_uid
        self.probe_combo.blockSignals(True)
        self.probe_combo.clear()
        self.probe_combo.addItems(probes)
        matching = next((probe for probe in probes if self.backend.normalize_probe_uid(probe) == preferred_uid), "")
        if matching:
            self.probe_combo.setCurrentText(matching)
        elif probes:
            self.probe_combo.setCurrentIndex(0)
        else:
            self.probe_combo.setCurrentIndex(-1)
        self.probe_combo.blockSignals(False)

    def _set_busy(self, busy: bool, action: str = "", status: str = "就绪") -> None:
        for button in self.action_buttons:
            button.setEnabled(not busy)
        text = f"执行中：{action}" if busy else status
        self.status_badge.setText(text)
        self.status_label.setText(text)
        if busy:
            self._set_badge_style("badgeRunning")
        elif status == "完成":
            self._set_badge_style("badgeSuccess")
        elif status in {"失败", "异常"}:
            self._set_badge_style("badgeError")
        else:
            self._set_badge_style("badgeReady")

    def _set_badge_style(self, name: str) -> None:
        self.status_badge.setObjectName(name)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

    def _append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text.rstrip() + "\n")

    def _clear_log(self) -> None:
        self.log_view.clear()

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def _set_combo_text(combo: QComboBox, text: str) -> None:
        if text:
            combo.setCurrentText(text)

    @staticmethod
    def _replace_combo_items(combo: QComboBox, values: list[str], current: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        combo.setCurrentText(current if current in values else values[0])
        combo.blockSignals(False)

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @staticmethod
    def _configure_chip_table(table: QTableWidget) -> None:
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(90)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        table.setColumnWidth(0, 300)
        table.setColumnWidth(1, 150)
        table.setColumnWidth(2, 160)
        table.setColumnWidth(3, 240)

    @staticmethod
    def _item(text: str, data=None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if data is not None:
            item.setData(Qt.UserRole, data)
        return item


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("DAP Flash Tool")
    app.setOrganizationName("DAPFlashTool")
    app.setStyle("Fusion")
    from .theme import QSS

    app.setStyleSheet(QSS)
    app.setWindowIcon(make_rounded_logo_icon())
    win = DapFlashApp()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
