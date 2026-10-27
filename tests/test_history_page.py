"""History master-detail browsing regression tests."""
import os
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.models import MeetingSummary, TranscriptionResult
from app.storage.library import LibraryService
from app.ui.library_page import LibraryPage
from app.ui.main_window import MainWindow


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


def test_history_selects_first_result_and_previews_business_content(tmp_path, qt_app):
    source = tmp_path / "meeting.wav"
    _write_wav(source)
    service = LibraryService(tmp_path / "workspace")
    record = service.create_record(source, title="Weekly planning")
    service.update_transcript(
        record.record_id,
        TranscriptionResult(text="Decide the release date", language="en"),
    )
    service.update_summary(
        record.record_id,
        MeetingSummary(overview="Release on Friday", markdown="# Release\nFriday"),
    )

    page = LibraryPage(service)
    page.refresh()
    qt_app.processEvents()

    assert page.table.columnCount() == 3
    assert page.selected_id() == record.record_id
    assert page.detail_title.text() == "Weekly planning"
    assert page.transcript_preview.toPlainText() == "Decide the release date"
    assert page.summary_preview.toPlainText() == "# Release\nFriday"
    assert page.load_button.isEnabled()
    page.close()


def test_history_search_empty_state_and_clear_filters(tmp_path, qt_app):
    source = tmp_path / "interview.wav"
    _write_wav(source)
    service = LibraryService(tmp_path / "workspace")
    service.create_record(source, title="Customer interview")
    page = LibraryPage(service)
    page.refresh()

    page.search_edit.setText("not present")
    qt_app.processEvents()
    assert page.table.rowCount() == 0
    assert page.list_stack.currentWidget() is page.empty_label
    assert not page.load_button.isEnabled()

    page.clear_filters()
    qt_app.processEvents()
    assert page.search_edit.text() == ""
    assert page.table.rowCount() == 1
    assert page.list_stack.currentWidget() is page.table
    page.close()


def test_stop_playback_releases_audio_before_record_is_moved(tmp_path, qt_app):
    source = tmp_path / "locked.wav"
    _write_wav(source)
    service = LibraryService(tmp_path / "workspace")
    record = service.create_record(source, title="Windows file handle")
    page = LibraryPage(service)
    page.refresh()
    qt_app.processEvents()

    assert not page.player.source().isEmpty()
    page.stop_playback()
    assert page.player.source().isEmpty()
    with pytest.raises(PermissionError):
        service.move_to_trash(record.record_id)
    assert not service.record_dir(record.record_id, trash=True).exists()

    QTest.qWait(250)
    service.move_to_trash(record.record_id)

    assert not service.record_dir(record.record_id).exists()
    assert service.record_dir(record.record_id, trash=True).exists()
    page.close()


def test_main_window_retries_trash_move_until_player_releases_file(
    tmp_path, monkeypatch, qt_app
):
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(
        "app.ui.main_window.load_config",
        lambda: AppConfig(workspace_dir=str(workspace)),
    )
    source = tmp_path / "retry.wav"
    _write_wav(source)
    window = MainWindow()
    record = window._library.create_record(source, title="Retry locked media")
    window._history_page.refresh()
    qt_app.processEvents()

    window._trash_record(record.record_id)
    assert not window._history_page.delete_button.isEnabled()
    assert window._history_page.delete_button.text() == "Moving to trash…"
    QTest.qWait(500)

    assert record.record_id not in window._trash_moves_pending
    assert window._history_page.delete_button.text() == "Move to trash"
    assert not window._library.record_dir(record.record_id).exists()
    assert window._library.record_dir(record.record_id, trash=True).exists()
    window.close()


@pytest.mark.parametrize("language", ("en", "zh-CN", "es"))
def test_compact_history_controls_fit_minimum_window_in_every_language(
    language, tmp_path, monkeypatch, qt_app
):
    workspace = tmp_path / language / "workspace"
    monkeypatch.setattr(
        "app.ui.main_window.load_config",
        lambda: AppConfig(ui_language=language, workspace_dir=str(workspace)),
    )
    source = tmp_path / language / "recording.wav"
    source.parent.mkdir(parents=True)
    _write_wav(source)
    window = MainWindow()
    window.resize(window.minimumSize())
    record = window._library.create_record(source, title="Long planning discussion")
    window._history_page.refresh()
    window._pages.setCurrentWidget(window._history_page)
    window.show()
    qt_app.processEvents()
    page = window._history_page

    assert not page.filter_panel.isVisible()
    assert not page.detail_panel.isVisible()
    assert page.list_stack.width() > page.width() * 0.9
    for control in (
        page.load_button,
        page.play_button,
        page.preview_button,
        page.more_button,
        page.delete_button,
    ):
        assert control.isVisible()
        assert control.width() >= control.sizeHint().width()
    assert not hasattr(page, "delete_action")

    page.filter_toggle_button.setChecked(True)
    page.preview_button.setChecked(True)
    qt_app.processEvents()
    assert page.filter_panel.isVisible()
    assert page.detail_panel.isVisible()
    assert page.selected_id() == record.record_id
    window.close()
