"""PDF summary export and compact workspace layout tests."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPalette
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.models import MeetingSummary
from app.services.pdf_export import export_summary_pdf
from app.services.summarization_service import render_summary_markdown
from app.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _summary(*, language: str = "zh-CN", repetitions: int = 1) -> MeetingSummary:
    summary = MeetingSummary(
        title="产品发布评审",
        overview="团队确认发布范围，并复核了风险。 " * repetitions,
        key_points=["中文、Español 与 special characters 都应完整显示。"] * repetitions,
        decisions=["按计划发布。"],
        action_items=[{
            "task": "完成行动项说明 " + "需要自动换行。" * repetitions,
            "owner": "王小明",
            "deadline": None,
            "status": "进行中",
        }],
        language=language,
        model="gpt-5-mini",
        length="long",
        generated_at="2026-09-01T10:30:00+08:00",
    )
    summary.markdown = render_summary_markdown(summary)
    return summary


@pytest.mark.parametrize("repetitions", [1, 90])
def test_pdf_export_creates_readable_single_and_multi_page_files(
    tmp_path: Path, qt_app, repetitions: int
):
    destination = tmp_path / f"summary-{repetitions}.pdf"
    returned_pages = export_summary_pdf(
        destination,
        _summary(repetitions=repetitions),
        record_title="秋季发布会议",
        source_file="release-review.wav",
    )
    document = QPdfDocument()
    error = document.load(str(destination))

    assert error == QPdfDocument.Error.None_
    assert document.pageCount() == returned_pages
    assert returned_pages >= (2 if repetitions > 1 else 1)
    assert destination.stat().st_size > 1_000


def test_pdf_export_forces_dark_text_on_white_pages_in_dark_mode(
    tmp_path: Path, qt_app
):
    original_palette = qt_app.palette()
    dark_palette = QPalette(original_palette)
    dark_palette.setColor(QPalette.ColorRole.Window, QColor("#202020"))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor("#202020"))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
    qt_app.setPalette(dark_palette)
    destination = tmp_path / "dark-mode-summary.pdf"
    try:
        export_summary_pdf(
            destination,
            _summary(),
            record_title="Dark mode regression",
            source_file="meeting.wav",
        )
    finally:
        qt_app.setPalette(original_palette)

    document = QPdfDocument()
    assert document.load(str(destination)) == QPdfDocument.Error.None_
    image = document.render(0, QSize(600, 849))
    sampled = [
        image.pixelColor(x, y).lightness()
        for y in range(0, image.height(), 4)
        for x in range(0, image.width(), 4)
    ]
    assert sum(value >= 245 for value in sampled) > len(sampled) * 0.55
    assert sum(value <= 100 for value in sampled) > 100


def test_workspace_settings_are_scoped_to_their_pages(
    tmp_path: Path, monkeypatch, qt_app
):
    monkeypatch.setattr(
        "app.ui.main_window.load_config",
        lambda: AppConfig(workspace_dir=str(tmp_path / "workspace")),
    )
    window = MainWindow()
    window.resize(980, 700)
    window.show()
    qt_app.processEvents()

    assert window._transcription_settings_panel.isVisible()
    assert not window._summary_settings_panel.isVisible()
    assert not window._cancel_button.isVisible()
    assert window._transcription_settings_panel.width() <= window._pages.width()
    window._show_summary_page()
    qt_app.processEvents()
    assert not window._transcription_settings_panel.isVisible()
    assert window._summary_settings_panel.isVisible()
    assert window._summary_generation_language.parentWidget() is not None
    window.close()
