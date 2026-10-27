"""GUI localization and language persistence tests."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.config import AppConfig, load_config
from app.i18n import TRANSLATIONS, normalize_language, tr
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_translation_catalogs_have_identical_keys():
    english_keys = set(TRANSLATIONS["en"])
    assert english_keys == set(TRANSLATIONS["zh-CN"])
    assert english_keys == set(TRANSLATIONS["es"])
    assert tr("zh-CN", "transcribe") == "开始转录"
    assert tr("es", "settings") == "Configuración"
    assert normalize_language("unsupported") == "en"


def test_settings_persists_interface_language(tmp_path, monkeypatch, qt_app):
    app_data = tmp_path / "appdata"
    app_data.mkdir()
    monkeypatch.setenv("APPDATA", str(app_data))
    config = AppConfig(workspace_dir=str(tmp_path / "workspace"))
    dialog = SettingsDialog(config)
    dialog.ui_language.setCurrentIndex(dialog.ui_language.findData("es"))

    dialog.accept()

    assert dialog.config.ui_language == "es"
    assert load_config().ui_language == "es"
    dialog.close()


def test_whisper_large_v3_is_available_in_settings_and_workspace(
    monkeypatch, tmp_path, qt_app
):
    config = AppConfig(workspace_dir=str(tmp_path / "workspace"))
    dialog = SettingsDialog(config)
    assert dialog.transcription_model.findText("whisper-large-v3") >= 0
    dialog.close()

    monkeypatch.setattr("app.ui.main_window.load_config", lambda: config)
    window = MainWindow()
    assert window._asr_model_selector.findData("whisper-large-v3") >= 0
    window._asr_model_selector.setCurrentIndex(
        window._asr_model_selector.findData("whisper-large-v3")
    )
    assert window._asr_model_selector.currentData() == "whisper-large-v3"
    assert not hasattr(window, "_asr_provider_selector")
    assert not hasattr(dialog, "provider")
    window.close()


def test_summary_generation_options_and_full_page_navigation(
    monkeypatch, tmp_path, qt_app
):
    config = AppConfig(workspace_dir=str(tmp_path / "workspace"))
    monkeypatch.setattr("app.ui.main_window.load_config", lambda: config)
    window = MainWindow()

    assert [
        window._summary_model_selector.itemData(index)
        for index in range(window._summary_model_selector.count())
    ] == ["gpt-5-mini", "deepseek-v4-flash", "gpt-5.4-low"]
    assert [
        window._summary_length_selector.itemData(index)
        for index in range(window._summary_length_selector.count())
    ] == ["short", "medium", "long"]
    assert window._summary_length_selector.currentData() == "medium"
    assert window._summary_generation_language.count() == 3
    assert window._workspace_stack.currentIndex() == 0

    window._summary_entry_button.click()
    assert window._workspace_stack.currentIndex() == 1
    window._back_to_transcript_button.click()
    assert window._workspace_stack.currentIndex() == 0
    saved = []
    monkeypatch.setattr("app.ui.main_window.save_config", saved.append)
    window._summary_model_selector.setCurrentIndex(
        window._summary_model_selector.findData("deepseek-v4-flash")
    )
    window._summary_generation_language.setCurrentIndex(
        window._summary_generation_language.findData("es")
    )
    window._summary_length_selector.setCurrentIndex(
        window._summary_length_selector.findData("short")
    )
    assert window._persist_summary_generation_defaults()
    assert saved[0].summary_model == "deepseek-v4-flash"
    assert saved[0].summary_language == "es"
    assert saved[0].summary_length == "short"
    window.close()

    configured = AppConfig(
        workspace_dir=str(tmp_path / "configured-workspace"),
        summary_model="deepseek-v4-flash",
        summary_language="es",
        summary_length="long",
    )
    monkeypatch.setattr("app.ui.main_window.load_config", lambda: configured)
    configured_window = MainWindow()
    assert configured_window._summary_model_selector.currentData() == (
        "deepseek-v4-flash"
    )
    assert configured_window._summary_generation_language.currentData() == "es"
    assert configured_window._summary_length_selector.currentData() == "long"
    configured_window.close()


def test_settings_exposes_summary_defaults(tmp_path, qt_app):
    dialog = SettingsDialog(
        AppConfig(workspace_dir=str(tmp_path / "workspace"))
    )

    assert dialog.summary_model.findData("gpt-5.4-low") >= 0
    assert dialog.summary_model.findData("deepseek-v4-flash") >= 0
    assert dialog.summary_model.findData("gpt-5-mini") >= 0
    assert dialog.summary_model.currentData() == "gpt-5-mini"
    assert dialog.summary_length.currentData() == "medium"
    assert dialog.summary_language.count() == 3
    dialog.close()


def test_main_window_retranslates_without_losing_mode(monkeypatch, qt_app):
    config = AppConfig(ui_language="zh-CN", default_mode="meeting")
    monkeypatch.setattr("app.ui.main_window.load_config", lambda: config)
    window = MainWindow()

    assert window._import_button.text() == "导入音频"
    assert window._record_button.text() == "录制会议（含麦克风）"
    assert window._mode_selector.currentData() == "meeting"
    assert window._summary_title.text() == "会议摘要"
    assert window._floating_button.text() == "缩成录音浮球"
    assert window._floating_recorder.stop_button.toolTip() == "停止录制"

    window._language = "es"
    window._retranslate_ui()
    assert window._import_button.text() == "Importar audio"
    assert window._record_button.text() == "Grabar reunión"
    assert window._mode_selector.currentData() == "meeting"
    assert window._summary_title.text() == "Resumen"
    assert window._floating_button.text() == "Reducir al control flotante"
    assert window._floating_recorder.stop_button.toolTip() == "Detener grabación"
    window.close()
