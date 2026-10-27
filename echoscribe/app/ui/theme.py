"""Notion-inspired warm-neutral visual theme."""

APP_STYLESHEET = """
QWidget {
    color: #37352f;
    background: #ffffff;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 14px;
}
QMainWindow { background: #ffffff; }
QLabel { background: transparent; }
QFrame#sidebar {
    background: #f7f7f5;
    border-right: 1px solid #e9e9e7;
}
QLabel#brand {
    font-size: 20px;
    font-weight: 600;
    letter-spacing: -0.4px;
}
QLabel#brandMark { background: transparent; }
QLabel#tagline, QLabel#eyebrow, QLabel#fileMeta { color: #787774; }
QLabel#pageTitle { font-size: 28px; font-weight: 650; letter-spacing: -0.7px; }
QLabel#sectionTitle { font-size: 15px; font-weight: 600; }
QLabel#detailTitle { font-size: 19px; font-weight: 650; letter-spacing: -0.3px; }
QLabel#emptyState {
    color: #787774;
    background: #fbfbfa;
    border: 1px dashed #dededb;
    border-radius: 8px;
    padding: 32px;
}
QLabel#status {
    color: #5f5e5b;
    background: #f7f7f5;
    border-radius: 4px;
    padding: 5px 9px;
}
QFrame#filePanel {
    background: #fbfbfa;
    border: 1px solid #e9e9e7;
    border-radius: 6px;
}
QFrame#settingsPanel {
    background: #f8f7f4;
    border: 1px solid #e5e1da;
    border-radius: 7px;
}
QPushButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 7px 10px;
    text-align: left;
    font-weight: 500;
}
QPushButton:hover { background: #efefed; }
QPushButton:pressed { background: #e7e7e4; padding-top: 8px; padding-bottom: 6px; }
QPushButton:focus { border: 1px solid #9b9a97; }
QPushButton:disabled { color: #b4b4b0; background: transparent; }
QPushButton[nav="true"] { padding: 8px 10px; }
QPushButton[nav="true"][active="true"] {
    background: #ebeae7;
    font-weight: 600;
}
QPushButton#primaryButton {
    color: #ffffff;
    background: #37352f;
    padding: 8px 14px;
    text-align: center;
}
QPushButton#primaryButton:hover { background: #4b4943; }
QPushButton#primaryButton:pressed { background: #2f2e2a; }
QPushButton#summaryButton {
    color: #403a32;
    background: #eee8dc;
    border: 1px solid #d8cdbb;
    padding: 8px 14px;
    text-align: center;
    font-weight: 600;
}
QPushButton#summaryButton:hover {
    background: #e5ddcf;
    border-color: #c8baa4;
}
QPushButton#summaryButton:pressed {
    background: #dcd2c1;
    padding-top: 9px;
    padding-bottom: 7px;
}
QPushButton#summaryButton:disabled {
    color: #aaa49b;
    background: #f5f3ef;
    border-color: #ebe7df;
}
QPushButton#summaryEntry {
    color: #403a32;
    background: #f7f3eb;
    border: 1px solid #e4dccf;
    border-radius: 6px;
    padding: 12px 14px;
    text-align: left;
    font-weight: 600;
}
QPushButton#summaryEntry:hover {
    background: #eee8dc;
    border-color: #d8cdbb;
}
QPushButton#translationButton {
    color: #4f473d;
    background: #f5f1e9;
    border: 1px solid #ded5c6;
    padding: 7px 11px;
    text-align: center;
}
QPushButton#translationButton:hover {
    background: #ece5d9;
    border-color: #cfc2ae;
}
QPushButton#translationButton:pressed { background: #e2d8c8; }
QPushButton#translationButton:disabled {
    color: #b4b4b0;
    background: transparent;
    border-color: transparent;
}
QPushButton#exportButton {
    color: #5f5e5b;
    background: transparent;
    border: 1px solid #dededb;
    padding: 6px 9px;
    text-align: center;
}
QPushButton#exportButton:hover { color: #37352f; background: #f7f7f5; }
QPushButton#exportButton:pressed { background: #efefed; }
QPushButton#exportButton:disabled { color: #b4b4b0; border-color: #efefed; }
QToolButton#exportButton {
    color: #5f5e5b;
    background: transparent;
    border: 1px solid #dededb;
    border-radius: 4px;
    padding: 6px 9px;
    font-weight: 500;
}
QToolButton#exportButton:hover { color: #37352f; background: #f7f7f5; }
QToolButton#exportButton:pressed { background: #efefed; }
QToolButton#exportButton:disabled { color: #b4b4b0; border-color: #efefed; }
QPushButton#dangerButton {
    color: #9f2d24;
    background: #fff7f5;
    border: 1px solid #efd8d4;
    padding: 7px 11px;
    text-align: center;
}
QPushButton#dangerButton:hover {
    color: #8f241c;
    background: #fcebe8;
    border-color: #dfbdb7;
}
QPushButton#dangerButton:pressed {
    background: #f7ddd9;
    padding-top: 8px;
    padding-bottom: 6px;
}
QPushButton#dangerButton:focus { border-color: #bd6b61; }
QPushButton#dangerButton:disabled {
    color: #b4b4b0;
    background: #faf9f8;
    border-color: #eceae8;
}
QPushButton#compactButton {
    color: #5f5e5b;
    background: #f7f7f5;
    border-color: #e9e9e7;
    text-align: center;
}
QPushButton#compactButton:checked {
    color: #403a32;
    background: #e9e4da;
    border-color: #cfc5b6;
    font-weight: 600;
}
QPushButton#compactButton:checked:hover { background: #e2dbcf; }
QToolButton#moreButton {
    color: #5f5e5b;
    background: #f7f7f5;
    border: 1px solid #e9e9e7;
    border-radius: 4px;
    padding: 7px 12px;
    font-weight: 500;
}
QToolButton#moreButton:hover { color: #37352f; background: #efefed; }
QToolButton#moreButton:pressed { background: #e7e7e4; }
QToolButton#moreButton:disabled { color: #b4b4b0; background: transparent; }
QMenu {
    background: #ffffff;
    border: 1px solid #dededb;
    padding: 5px;
}
QMenu::item { border-radius: 3px; padding: 7px 28px 7px 10px; }
QMenu::item:selected { background: #efefed; }
QPushButton#floatingButton {
    color: #5b5145;
    background: #eeeae2;
    border: 1px solid #dfd8cc;
    text-align: center;
}
QPushButton#floatingButton:hover {
    color: #37352f;
    background: #e7e1d7;
    border-color: #cfc5b6;
}
QPushButton#floatingButton:pressed {
    background: #ddd5c8;
    padding-top: 8px;
    padding-bottom: 6px;
}
QPushButton#floatingButton:disabled {
    color: #aaa49b;
    background: #f5f3ef;
    border-color: #ebe7df;
}
QComboBox, QLineEdit, QSpinBox {
    background: #ffffff;
    border: 1px solid #dededb;
    border-radius: 4px;
    padding: 7px 9px;
    selection-background-color: #d9e7f5;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover { border-color: #b9b9b5; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 1px solid #787774; }
QComboBox::drop-down { border: none; width: 24px; }
QTextEdit {
    background: #ffffff;
    border: none;
    padding: 10px 2px;
    selection-background-color: #d9e7f5;
    font-size: 15px;
    line-height: 1.45;
}
QTextEdit#summaryDocument {
    color: #37352f;
    background: #fdfcfb;
    border: 1px solid #ebe7e0;
    border-radius: 7px;
    padding: 4px;
    font-size: 15px;
}
QPlainTextEdit {
    color: #4b4943;
    background: #fbfbfa;
    border: none;
    padding: 10px;
    selection-background-color: #d9e7f5;
    font-size: 13px;
    line-height: 1.4;
}
QProgressBar { border: none; background: #efefed; max-height: 3px; }
QProgressBar::chunk { background: #37352f; }
QSplitter::handle { background: #e9e9e7; width: 1px; }
QSplitter#historyBrowser::handle { background: transparent; height: 6px; }
QDialog { background: #ffffff; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QTableWidget {
    background: #ffffff;
    alternate-background-color: #fbfbfa;
    border: 1px solid #e9e9e7;
    border-radius: 6px;
    gridline-color: #efefed;
    selection-background-color: #ebeae7;
    selection-color: #37352f;
}
QTableWidget::item { padding: 7px 9px; }
QTableWidget::item:selected { border-left: 3px solid #5b5145; }
QHeaderView::section {
    color: #787774;
    background: #f7f7f5;
    border: none;
    border-bottom: 1px solid #e9e9e7;
    padding: 8px;
    font-weight: 600;
}
QFrame#historyDetail {
    background: #fbfbfa;
    border: 1px solid #e9e9e7;
    border-radius: 8px;
}
QFrame#historyFilters {
    background: #fbfbfa;
    border: 1px solid #e9e9e7;
    border-radius: 6px;
}
QTabWidget::pane {
    background: #fbfbfa;
    border: 1px solid #e9e9e7;
    border-radius: 5px;
    top: -1px;
}
QTabBar::tab {
    color: #787774;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 7px 10px;
    font-weight: 500;
}
QTabBar::tab:hover { color: #37352f; background: #efefed; }
QTabBar::tab:selected { color: #37352f; border-bottom-color: #5b5145; }
QSlider::groove:horizontal { height: 3px; background: #dededb; }
QSlider::handle:horizontal {
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
    background: #5f5e5b;
}
"""
