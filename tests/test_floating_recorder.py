"""Tests for the compact recording controller and waveform."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.floating_recorder import FloatingRecorderWidget, WaveformWidget
from app.config import AppConfig
from app.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_waveform_smooths_attack_and_release(qt_app):
    waveform = WaveformWidget()
    waveform.set_level(0.8)
    waveform._animate()
    attacked = waveform.display_level
    assert 0 < attacked < 0.8

    waveform.set_level(0)
    waveform._animate()
    assert 0 <= waveform.display_level < attacked
    waveform.close()


def test_floating_recorder_time_stop_and_restore_signals(qt_app):
    widget = FloatingRecorderWidget()
    events = []
    widget.restore_requested.connect(lambda: events.append("restore"))
    widget.stop_requested.connect(lambda: events.append("stop"))
    widget.set_elapsed_seconds(65)
    assert widget.elapsed_label.text() == "01:05"

    QTest.mouseClick(widget.stop_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(10, 30))

    assert events == ["stop", "restore"]
    widget.close()


def test_floating_recorder_is_kept_inside_available_screen(qt_app):
    anchor = QWidget()
    anchor.show()
    widget = FloatingRecorderWidget()
    widget._last_position = QPoint(-100_000, -100_000)
    widget.show_near(anchor)
    qt_app.processEvents()

    available = widget.screen().availableGeometry()
    assert available.contains(widget.geometry())
    widget.hide()
    anchor.close()


def test_main_window_enters_and_restores_floating_mode(tmp_path, monkeypatch, qt_app):
    config = AppConfig(workspace_dir=str(tmp_path / "workspace"))
    monkeypatch.setattr("app.ui.main_window.load_config", lambda: config)
    window = MainWindow()
    window.show()
    window._task_kind = "recording"
    window._recording_active = True

    window._enter_floating_mode()
    qt_app.processEvents()
    assert window._floating_recorder.isVisible()
    assert not window.isVisible()

    window._restore_from_floating()
    qt_app.processEvents()
    assert window.isVisible()
    assert not window._floating_recorder.isVisible()
    window._recording_active = False
    window._task_kind = ""
    window.close()


def test_recording_start_automatically_enters_floating_mode(
    tmp_path, monkeypatch, qt_app
):
    config = AppConfig(workspace_dir=str(tmp_path / "workspace"))
    monkeypatch.setattr("app.ui.main_window.load_config", lambda: config)
    window = MainWindow()
    calls = []
    monkeypatch.setattr(window, "_enter_floating_mode", lambda: calls.append("float"))
    window._task_kind = "recording"

    window._on_recording_started()
    QTest.qWait(180)

    assert calls == ["float"]
    assert window._recording_active is True
    assert window._floating_button.isEnabled()
    window._record_timer.stop()
    window._recording_active = False
    window._task_kind = ""
    window.close()
