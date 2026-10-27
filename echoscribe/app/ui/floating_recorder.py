"""Always-on-top compact recorder controls with a live audio waveform."""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import QObject, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QCloseEvent, QGuiApplication, QMouseEvent, QPainter, QPainterPath,
)
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)


class RecordingLevelBridge(QObject):
    """Safely deliver recording-thread level values to the GUI thread."""

    level_changed = Signal(float)


class WaveformWidget(QWidget):
    """Render a smoothed, recent-history bar waveform."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(43, 30)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._target_level = 0.0
        self._display_level = 0.0
        self._history: deque[float] = deque([0.0] * 9, maxlen=9)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._animate)
        self._timer.start()

    @property
    def display_level(self) -> float:
        return self._display_level

    def set_level(self, level: float) -> None:
        """Set a normalized target level without forcing an immediate repaint."""
        self._target_level = max(0.0, min(1.0, float(level)))

    def reset(self) -> None:
        self._target_level = 0.0
        self._display_level = 0.0
        self._history = deque([0.0] * 9, maxlen=9)
        self.update()

    def _animate(self) -> None:
        coefficient = 0.65 if self._target_level > self._display_level else 0.16
        self._display_level += (
            self._target_level - self._display_level
        ) * coefficient
        if self._target_level < 0.004 and self._display_level < 0.006:
            self._display_level = 0.0
        # Ease quiet signals upward so speech remains legible without faking activity.
        visible_level = self._display_level ** 0.55 if self._display_level else 0.0
        self._history.append(visible_level)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        width = 3.0
        gap = 1.8
        center_y = self.height() / 2
        for index, level in enumerate(self._history):
            emphasis = 1.0 - abs(index - 4) * 0.065
            height = max(3.0, min(26.0, 3.0 + level * 23.0 * emphasis))
            x = 1.0 + index * (width + gap)
            painter.drawRoundedRect(
                QRectF(x, center_y - height / 2, width, height), 1.5, 1.5
            )


class StopRecordingButton(QPushButton):
    """Draw the stop glyph independently of installed fonts."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        size = 7.0
        painter.drawRoundedRect(
            QRectF(
                (self.width() - size) / 2,
                (self.height() - size) / 2,
                size,
                size,
            ),
            1.2,
            1.2,
        )


class FloatingRecorderWidget(QWidget):
    """Compact draggable recording capsule shown instead of the main window."""

    restore_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(176, 68)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_origin: QPoint | None = None
        self._window_origin: QPoint | None = None
        self._moved = False
        self._last_position: QPoint | None = None

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(55, 50, 42, 95))
        self.setGraphicsEffect(shadow)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 11, 10)
        layout.setSpacing(8)
        self.recording_dot = QLabel()
        self.recording_dot.setFixedSize(8, 8)
        self.recording_dot.setStyleSheet(
            "background:#ef4444;border-radius:4px;"
        )
        self.recording_dot.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.waveform = WaveformWidget(self)
        self.elapsed_label = QLabel("00:00")
        self.elapsed_label.setStyleSheet(
            "color:#f5f3ee;background:transparent;font-family:'Cascadia Mono',"
            "'Consolas';font-size:12px;font-weight:600;"
        )
        self.elapsed_label.setMinimumWidth(39)
        self.elapsed_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.stop_button = StopRecordingButton()
        self.stop_button.setFixedSize(30, 30)
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.setStyleSheet(
            "QPushButton{color:#ffffff;background:#ef4444;border:none;"
            "border-radius:15px;padding:0;text-align:center;font-size:10px;}"
            "QPushButton:hover{background:#dc2626;}"
            "QPushButton:pressed{background:#b91c1c;padding-top:1px;}"
            "QPushButton:focus{border:2px solid #fecaca;}"
            "QPushButton:disabled{background:#6b7280;}"
        )
        self.stop_button.clicked.connect(self.stop_requested.emit)
        layout.addWidget(self.recording_dot)
        layout.addWidget(self.waveform)
        layout.addWidget(self.elapsed_label)
        layout.addWidget(self.stop_button)

    def set_texts(self, *, restore: str, stop: str, recording: str) -> None:
        self.setToolTip(restore)
        self.waveform.setToolTip(restore)
        self.elapsed_label.setToolTip(recording)
        self.stop_button.setToolTip(stop)
        self.stop_button.setAccessibleName(stop)
        self.setAccessibleName(recording)

    def reset(self) -> None:
        self.waveform.reset()
        self.elapsed_label.setText("00:00")
        self.stop_button.setEnabled(True)

    def set_level(self, level: float) -> None:
        self.waveform.set_level(level)

    def set_elapsed_seconds(self, seconds: int) -> None:
        seconds = max(0, seconds)
        if seconds < 3600:
            value = f"{seconds // 60:02d}:{seconds % 60:02d}"
        else:
            value = f"{seconds // 3600:d}:{seconds % 3600 // 60:02d}"
        self.elapsed_label.setText(value)

    def show_near(self, anchor: QWidget) -> None:
        """Show at the remembered position or the anchor screen's top-right."""
        screen = anchor.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        if self._last_position is None:
            position = QPoint(
                available.right() - self.width() - 24,
                available.top() + 24,
            )
        else:
            position = self._clamped_position(self._last_position)
        self.move(position)
        self.show()
        self.raise_()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 23, 23)
        painter.fillPath(path, QColor("#24231f"))
        painter.setPen(QColor(255, 255, 255, 28))
        painter.drawPath(path)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            self._window_origin = self.pos()
            self._moved = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None and self._window_origin is not None:
            delta = event.globalPosition().toPoint() - self._drag_origin
            if delta.manhattanLength() > 4:
                self._moved = True
            position = self._clamped_position(self._window_origin + delta)
            self.move(position)
            self._last_position = position
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_origin is not None:
            should_restore = not self._moved
            self._drag_origin = None
            self._window_origin = None
            self._last_position = self.pos()
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            if should_restore:
                self.restore_requested.emit()
            return
        super().mouseReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.restore_requested.emit()

    def _clamped_position(self, position: QPoint) -> QPoint:
        center = position + QPoint(self.width() // 2, self.height() // 2)
        screen = QGuiApplication.screenAt(center) or self.screen()
        if screen is None:
            return position
        area = screen.availableGeometry()
        return QPoint(
            min(max(position.x(), area.left()), area.right() - self.width() + 1),
            min(max(position.y(), area.top()), area.bottom() - self.height() + 1),
        )
