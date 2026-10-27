"""Minimal brand assets and translated layout regression tests."""
import os
from xml.etree import ElementTree

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.i18n import TRANSLATIONS
from app.ui.icons import asset_path, logo_icon, svg_icon
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_svg_asset_set_is_valid_and_loadable():
    names = {
        "workspace", "history", "trash", "import", "record", "floating",
        "settings", "folder", "transcribe", "transcribe_light", "summary",
        "translate", "copy", "cancel", "play", "rename", "save_light",
        "workspace_light", "trash_danger",
        "export",
    }
    ElementTree.parse(asset_path("logo.svg"))
    assert not logo_icon().isNull()
    for name in names:
        path = asset_path(f"icons/{name}.svg")
        assert path.is_file(), name
        root = ElementTree.parse(path).getroot()
        assert root.attrib["viewBox"] == "0 0 24 24"
        assert not svg_icon(name).isNull()


@pytest.mark.parametrize("language", TRANSLATIONS)
def test_sidebar_fits_each_gui_language(language, monkeypatch, qt_app):
    config = AppConfig(ui_language=language)
    monkeypatch.setattr("app.ui.main_window.load_config", lambda: config)
    window = MainWindow()
    window.show()
    qt_app.processEvents()

    buttons = (
        window._workspace_nav, window._history_nav, window._trash_nav,
        window._import_button, window._record_button, window._floating_button,
        window._settings_button, window._open_folder_button,
    )
    available = window._sidebar.width() - 32
    assert all(button.sizeHint().width() <= available for button in buttons)
    assert window._mode_selector.width() >= window._mode_selector.minimumWidth()
    workspace_actions = (
        window._transcribe_button,
        window._summary_button,
        window._translate_transcript_button,
        window._translate_summary_button,
        window._export_transcript_button,
        window._export_summary_button,
    )
    assert all(control.width() >= control.sizeHint().width() for control in workspace_actions)
    assert window._summary_button.objectName() == "summaryButton"
    assert not window.windowIcon().isNull()
    window.close()


@pytest.mark.parametrize("language", TRANSLATIONS)
def test_settings_options_fit_each_gui_language(language, tmp_path, qt_app):
    dialog = SettingsDialog(
        AppConfig(ui_language=language, workspace_dir=str(tmp_path / "workspace"))
    )
    dialog.show()
    qt_app.processEvents()

    assert dialog.provider_chunking.width() >= dialog.provider_chunking.sizeHint().width()
    assert dialog.copy_source.width() >= dialog.copy_source.sizeHint().width()
    dialog.close()
