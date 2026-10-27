"""Workspace translation controls and current-version export tests."""
import os
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.models import MeetingSummary, TranscriptionResult, TranslationVersion
from app.ui.main_window import MainWindow, _safe_export_stem


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 400)


def _window_with_translations(tmp_path, monkeypatch) -> tuple[MainWindow, str]:
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(
        "app.ui.main_window.load_config",
        lambda: AppConfig(workspace_dir=str(workspace)),
    )
    source = tmp_path / "meeting.wav"
    _write_wav(source)
    window = MainWindow()
    record = window._library.create_record(source, title='Plan: August / "launch"')
    window._library.update_transcript(
        record.record_id,
        TranscriptionResult(text="Original transcript", language="en"),
    )
    window._library.update_summary(
        record.record_id,
        MeetingSummary(markdown="# Original summary\n\nDecision"),
    )
    window._library.save_translation(
        record.record_id,
        "transcript",
        TranslationVersion(
            language="es",
            created_at="2026-08-04T00:00:00Z",
            model="test",
            text="Transcripción traducida",
        ),
    )
    window._library.save_translation(
        record.record_id,
        "summary",
        TranslationVersion(
            language="es",
            created_at="2026-08-04T00:00:00Z",
            model="test",
            summary=MeetingSummary(markdown="# Resumen traducido\n\nDecisión"),
        ),
    )
    window._load_record(record.record_id)
    return window, record.record_id


def test_translation_controls_follow_source_and_selected_version(
    tmp_path, monkeypatch, qt_app
):
    window, _ = _window_with_translations(tmp_path, monkeypatch)

    assert not window._translate_transcript_button.isEnabled()
    assert not window._translate_summary_button.isEnabled()
    assert window._export_transcript_button.isEnabled()
    assert window._export_summary_button.isEnabled()

    window._transcript_language.setCurrentIndex(
        window._transcript_language.findData("zh-CN")
    )
    assert window._translate_transcript_button.isEnabled()
    assert not window._export_transcript_button.isEnabled()

    window._transcript_language.setCurrentIndex(
        window._transcript_language.findData("es")
    )
    assert window._text_area.toPlainText() == "Transcripción traducida"
    assert window._translate_transcript_button.isEnabled()
    assert window._export_transcript_button.isEnabled()
    window.close()


def test_exports_selected_transcript_and_summary_translation(
    tmp_path, monkeypatch, qt_app
):
    window, _ = _window_with_translations(tmp_path, monkeypatch)
    window._transcript_language.setCurrentIndex(
        window._transcript_language.findData("es")
    )
    window._summary_language.setCurrentIndex(window._summary_language.findData("es"))

    transcript_target = tmp_path / "exports" / "transcript"
    monkeypatch.setattr(
        "app.ui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(transcript_target), ""),
    )
    window._export_current_content("transcript")
    assert transcript_target.with_suffix(".txt").read_text(encoding="utf-8") == (
        "Transcripción traducida\n"
    )

    summary_target = tmp_path / "exports" / "summary"
    monkeypatch.setattr(
        "app.ui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(summary_target), ""),
    )
    window._export_current_content("summary")
    assert summary_target.with_suffix(".md").read_text(encoding="utf-8") == (
        "# Resumen traducido\n\nDecisión\n"
    )
    window.close()


def test_pdf_export_uses_selected_summary_translation(
    tmp_path, monkeypatch, qt_app
):
    window, _ = _window_with_translations(tmp_path, monkeypatch)
    window._summary_language.setCurrentIndex(window._summary_language.findData("es"))
    target = tmp_path / "exports" / "translated-summary"
    monkeypatch.setattr(
        "app.ui.main_window.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(target), ""),
    )
    calls = []
    monkeypatch.setattr(
        "app.ui.main_window.export_summary_pdf",
        lambda destination, summary, **kwargs: calls.append(
            (destination, summary, kwargs)
        ),
    )

    window._export_pdf_action.trigger()

    assert calls[0][0] == target.with_suffix(".pdf")
    assert calls[0][1].markdown.startswith("# Resumen traducido")
    assert calls[0][2]["record_title"] == 'Plan: August / "launch"'
    assert window._export_markdown_action.text()
    window.close()


def test_export_filename_stem_is_windows_safe():
    assert _safe_export_stem('Plan: August / "launch"') == "Plan_ August _ _launch_"
