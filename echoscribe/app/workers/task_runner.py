"""Reusable cancellable QRunnable wrapper."""
from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

logger = logging.getLogger(__name__)


class CancellationToken:
    """Thread-safe cooperative cancellation flag."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()


class TaskSignals(QObject):
    started = Signal()
    result = Signal(object)
    error = Signal(object, str)
    cancelled = Signal()
    finished = Signal()


class TaskRunner(QRunnable):
    """Execute a callable on a Qt thread pool and deliver its outcome as signals."""

    def __init__(self, task: Callable[[CancellationToken], Any]) -> None:
        super().__init__()
        self.task = task
        self.token = CancellationToken()
        self.signals = TaskSignals()

    def cancel(self) -> None:
        self.token.cancel()

    @Slot()
    def run(self) -> None:
        self.signals.started.emit()
        try:
            if self.token.is_cancelled:
                self.signals.cancelled.emit()
                return
            result = self.task(self.token)
            if self.token.is_cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.result.emit(result)
        except Exception as exc:
            if self.token.is_cancelled:
                self.signals.cancelled.emit()
            else:
                logger.exception("Background task failed")
                self.signals.error.emit(exc, traceback.format_exc())
        finally:
            self.signals.finished.emit()
