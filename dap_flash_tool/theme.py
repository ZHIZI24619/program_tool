# -*- coding: utf-8 -*-
"""Global light/dark QSS matching SerialTool and RFID_Tool."""

QSS = """
QMainWindow, QWidget {
    background-color: #1e222a;
    color: #d4d8e0;
    font-size: 12px;
}
#mainWindow { border-radius: 10px; background-color: #1e222a; }
#mainWindow[winMaximized="true"] { border-radius: 0px; }
QToolBar {
    background-color: #232833;
    border: none;
    border-bottom: 1px solid #343a47;
    padding: 4px;
    spacing: 8px;
}
QGroupBox {
    border: 1px solid #343a47;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 4px;
    font-weight: bold;
    color: #c3c9d4;
    background: #20242d;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #8fd0ff;
}
QLabel { background: transparent; }
QComboBox, QSpinBox {
    background: #14171d;
    border: 1px solid #343a47;
    border-radius: 4px;
    padding: 3px 8px;
    min-height: 18px;
}
QComboBox:disabled, QSpinBox:disabled { color: #5a6170; background: #20242d; }
QComboBox QAbstractItemView {
    background: #1a1e26;
    border: 1px solid #343a47;
    selection-background-color: #2d6fdb;
    selection-color: #ffffff;
}
QLineEdit, QPlainTextEdit, QTableWidget {
    background: #14171d;
    border: 1px solid #343a47;
    border-radius: 4px;
    color: #e6e9ef;
    selection-background-color: #2d6fdb;
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #4a8bef; }
QPlainTextEdit {
    font-family: Consolas, "Courier New", "Microsoft YaHei Mono", monospace;
    font-size: 12px;
}
QHeaderView::section {
    background: #232833;
    color: #d4d8e0;
    border: none;
    border-right: 1px solid #343a47;
    border-bottom: 1px solid #343a47;
    padding: 5px 8px;
    font-weight: bold;
}
QTableWidget { gridline-color: #343a47; alternate-background-color: #181c24; }
QPushButton {
    background: #2a303b;
    border: 1px solid #3a4150;
    border-radius: 4px;
    padding: 4px 12px;
    color: #d4d8e0;
}
QPushButton:hover { background: #333a48; }
QPushButton:pressed { background: #22262f; }
QPushButton:disabled { color: #5a6170; background: #232833; }
QPushButton#btnPrimary {
    background: #1c5fa8;
    border-color: #3a86d8;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#btnPrimary:hover { background: #2372c4; }
QPushButton#btnDanger {
    background: #b3453f;
    border-color: #d65a53;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#btnDanger:hover { background: #c95049; }
QPushButton#btnUpdate {
    background: #c07a18;
    border-color: #e09a3c;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#btnUpdate:hover { background: #d18a20; }
QCheckBox { spacing: 6px; background: transparent; }
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #7a8291;
    border-radius: 3px;
    background: #14171d;
}
QCheckBox::indicator:hover { border-color: #8fd0ff; }
QCheckBox::indicator:checked {
    background: #2d6fdb;
    border-color: #4a8bef;
}
QCheckBox::indicator:checked:disabled {
    background: #2a303b;
    border-color: #5a6170;
}
QCheckBox::indicator:unchecked:disabled {
    background: #20242d;
    border-color: #4a5264;
}
QScrollBar:vertical { background: #1a1e26; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3a4150; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #4a5264; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #1a1e26; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #3a4150; border-radius: 5px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: #4a5264; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
#titleBar {
    background-color: #232833;
    border: none;
    border-bottom: 1px solid #343a47;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}
#titleBar[winMaximized="true"] { border-top-left-radius: 0px; border-top-right-radius: 0px; }
#titleLabel { color: #e6e9ef; font-weight: bold; font-size: 13px; padding-left: 6px; }
#titleBtn, #titleBtnClose {
    background: transparent;
    border: none;
    color: #b8bfcc;
    font-size: 15px;
    border-radius: 0;
    padding: 0;
}
#titleBtn:hover { background: #343a49; color: #ffffff; }
#titleBtnClose:hover { background: #d64545; color: #ffffff; }
#statusBar {
    background: #232833;
    border-top: 1px solid #343a47;
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
}
#statusBar QLabel { color: #9aa3b2; }
#statusClock { font-family: Consolas, "Courier New", monospace; }
#operationProgress {
    background: #151922;
    border: 1px solid #2c3442;
    border-radius: 7px;
    color: #e6e9ef;
    text-align: center;
    font-size: 10px;
}
#operationProgress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #1d4ed8, stop:0.5 #2d6fdb, stop:1 #4a8bef);
    border-radius: 6px;
    margin: 1px;
}
#operationProgress::chunk[state="success"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #059669, stop:0.5 #10b981, stop:1 #34d399);
}
#operationProgress::chunk[state="error"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #b91c1c, stop:0.5 #dc2626, stop:1 #ef4444);
}
#elapsedLabel { font-family: Consolas, "Courier New", monospace; }
#statusBar[winMaximized="true"] { border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; }
#hintLabel { color: #9aa3b2; }
#badgeReady, #badgeRunning, #badgeSuccess, #badgeError {
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: bold;
}
#badgeReady { color: #9aa3b2; background: #2a303b; }
#badgeRunning { color: #8fd0ff; background: #1c3a5e; }
#badgeSuccess { color: #3ddc84; background: #1c3f2d; }
#badgeError { color: #f0a0a0; background: #4a2320; }
"""


LIGHT_QSS = """
QMainWindow, QWidget {
    background-color: #f3f5f9;
    color: #2b3038;
    font-size: 12px;
}
#mainWindow { border-radius: 10px; background-color: #f3f5f9; }
#mainWindow[winMaximized="true"] { border-radius: 0px; }
QToolBar {
    background-color: #e9edf3;
    border: none;
    border-bottom: 1px solid #ccd3de;
    padding: 4px;
    spacing: 8px;
}
QGroupBox {
    border: 1px solid #ccd3de;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 4px;
    font-weight: bold;
    color: #3a414d;
    background: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #1f6dc4;
}
QLabel { background: transparent; }
QComboBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #c3cbd6;
    border-radius: 4px;
    padding: 3px 8px;
    min-height: 18px;
}
QComboBox:disabled, QSpinBox:disabled { color: #a0a7b2; background: #f0f2f6; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #c3cbd6;
    selection-background-color: #3d7ee8;
    selection-color: #ffffff;
}
QLineEdit, QPlainTextEdit, QTableWidget {
    background: #ffffff;
    border: 1px solid #c3cbd6;
    border-radius: 4px;
    color: #1f242b;
    selection-background-color: #3d7ee8;
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #4a8bef; }
QPlainTextEdit {
    font-family: Consolas, "Courier New", "Microsoft YaHei Mono", monospace;
    font-size: 12px;
}
QHeaderView::section {
    background: #e9edf3;
    color: #2b3038;
    border: none;
    border-right: 1px solid #ccd3de;
    border-bottom: 1px solid #ccd3de;
    padding: 5px 8px;
    font-weight: bold;
}
QTableWidget { gridline-color: #ccd3de; alternate-background-color: #f7f9fc; }
QPushButton {
    background: #ffffff;
    border: 1px solid #bcc5d1;
    border-radius: 4px;
    padding: 4px 12px;
    color: #2b3038;
}
QPushButton:hover { background: #eef1f6; }
QPushButton:pressed { background: #dfe5ee; }
QPushButton:disabled { color: #a0a7b2; background: #f0f2f6; }
QPushButton#btnPrimary {
    background: #2f6fcf;
    border-color: #4a86de;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#btnPrimary:hover { background: #3d7ee8; }
QPushButton#btnDanger {
    background: #c44842;
    border-color: #d65a53;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#btnDanger:hover { background: #d6554e; }
QPushButton#btnUpdate {
    background: #e08a1e;
    border-color: #f0a63c;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#btnUpdate:hover { background: #f09a28; }
QCheckBox { spacing: 6px; background: transparent; }
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #8a93a2;
    border-radius: 3px;
    background: #ffffff;
}
QCheckBox::indicator:hover { border-color: #3d7ee8; }
QCheckBox::indicator:checked {
    background: #3d7ee8;
    border-color: #2f6fcf;
}
QCheckBox::indicator:checked:disabled {
    background: #dfe5ee;
    border-color: #a0a7b2;
}
QCheckBox::indicator:unchecked:disabled {
    background: #f0f2f6;
    border-color: #c3cbd6;
}
QScrollBar:vertical { background: #f3f5f9; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #c3cbd6; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #aab4c2; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #f3f5f9; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #c3cbd6; border-radius: 5px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: #aab4c2; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
#titleBar {
    background-color: #e9edf3;
    border: none;
    border-bottom: 1px solid #ccd3de;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}
#titleBar[winMaximized="true"] { border-top-left-radius: 0px; border-top-right-radius: 0px; }
#titleLabel { color: #2b3038; font-weight: bold; font-size: 13px; padding-left: 6px; }
#titleBtn, #titleBtnClose {
    background: transparent;
    border: none;
    color: #5a6270;
    font-size: 15px;
    border-radius: 0;
    padding: 0;
}
#titleBtn:hover { background: #d6dce6; color: #1f242b; }
#titleBtnClose:hover { background: #d64545; color: #ffffff; }
#statusBar {
    background: #e9edf3;
    border-top: 1px solid #ccd3de;
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
}
#statusBar QLabel { color: #6a7280; }
#statusClock { font-family: Consolas, "Courier New", monospace; }
#operationProgress {
    background: #eef1f6;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    color: #1f242b;
    text-align: center;
    font-size: 10px;
}
#operationProgress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #2563eb, stop:0.5 #3b82f6, stop:1 #60a5fa);
    border-radius: 6px;
    margin: 1px;
}
#operationProgress::chunk[state="success"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #059669, stop:0.5 #10b981, stop:1 #34d399);
}
#operationProgress::chunk[state="error"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #dc2626, stop:0.5 #ef4444, stop:1 #f87171);
}
#elapsedLabel { font-family: Consolas, "Courier New", monospace; }
#statusBar[winMaximized="true"] { border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; }
#hintLabel { color: #6a7280; }
#badgeReady, #badgeRunning, #badgeSuccess, #badgeError {
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: bold;
}
#badgeReady { color: #475569; background: #e2e8f0; }
#badgeRunning { color: #1d4ed8; background: #dbeafe; }
#badgeSuccess { color: #15803d; background: #dcfce7; }
#badgeError { color: #b91c1c; background: #fee2e2; }
"""
