"""History and application-trash widgets."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models import LibraryRecord
from app.storage.library import LibraryService
from app.ui.icons import apply_icon

STATUS_COLORS = {
    "completed": "#2f6f4e",
    "failed": "#b42318",
    "transcribing": "#315f7d",
    "summarizing": "#7a5b2e",
    "cancelled": "#787774",
}


class LibraryPage(QWidget):
    """Searchable master-detail library with local audio playback."""

    load_requested = Signal(str)
    rename_requested = Signal(str)
    transcribe_requested = Signal(str)
    summarize_requested = Signal(str)
    open_folder_requested = Signal(str)
    trash_requested = Signal(str)

    def __init__(self, service: LibraryService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._records: list[LibraryRecord] = []
        self.status_texts: dict[str, str] = {}
        self.source_texts: dict[str, str] = {}
        self.count_template = "{count} recordings"
        self.no_results_text = "No matching recordings"
        self.no_selection_text = "Select a recording to see its details."
        self.no_transcript_text = "No transcript yet."
        self.no_summary_text = "No summary yet."
        self.file_template = "File: {value}"
        self.source_template = "Source: {value}"
        self.language_template = "Language: {value}"
        self.created_template = "Created: {value}"
        self.unavailable_text = "Unavailable"
        self.filters_text = "Filters"
        self.show_preview_text = "Show preview"
        self.hide_preview_text = "Hide preview"
        self.more_actions_text = "More actions"
        self.move_to_trash_text = "Move to trash"
        self.moving_to_trash_text = "Moving to trash…"
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 36, 26)
        layout.setSpacing(12)
        self.title_label = QLabel("History")
        self.title_label.setObjectName("pageTitle")
        layout.addWidget(self.title_label)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText(
            "Search title, file, transcript, summary, or translation…"
        )
        self.filter_toggle_button = QPushButton("Filters")
        self.filter_toggle_button.setObjectName("compactButton")
        self.filter_toggle_button.setCheckable(True)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.filter_toggle_button)
        layout.addLayout(search_row)

        self.filter_panel = QFrame()
        self.filter_panel.setObjectName("historyFilters")
        filters = QGridLayout(self.filter_panel)
        filters.setContentsMargins(10, 10, 10, 10)
        filters.setHorizontalSpacing(8)
        filters.setVerticalSpacing(8)
        self.status_filter = QComboBox()
        self.status_filter.addItem("All statuses", "")
        for value in (
            "created", "transcribing", "summarizing", "completed", "failed", "cancelled"
        ):
            self.status_filter.addItem(value.title(), value)
        self.source_filter = QComboBox()
        self.source_filter.addItem("All sources", "")
        self.source_filter.addItem("Imported", "import")
        self.source_filter.addItem("PC recordings", "pc_recording")
        self.language_filter = QComboBox()
        self.language_filter.addItem("All languages", "")
        for value in ("en", "zh-CN", "es"):
            self.language_filter.addItem(value, value)
        self.sort_filter = QComboBox()
        self.sort_filter.addItem("Newest", "newest")
        self.sort_filter.addItem("Oldest", "oldest")
        self.sort_filter.addItem("Title", "title")
        filters.addWidget(self.status_filter, 0, 0)
        filters.addWidget(self.source_filter, 0, 1)
        filters.addWidget(self.language_filter, 1, 0)
        filters.addWidget(self.sort_filter, 1, 1)
        self.clear_filters_button = QPushButton("Clear filters")
        self.clear_filters_button.setObjectName("compactButton")
        filters.addWidget(self.clear_filters_button, 2, 1, Qt.AlignmentFlag.AlignRight)
        for column in range(2):
            filters.setColumnStretch(column, 1)
        self.filter_panel.hide()
        layout.addWidget(self.filter_panel)

        self.result_count_label = QLabel(self.count_template.format(count=0))
        self.result_count_label.setObjectName("eyebrow")
        layout.addWidget(self.result_count_label)

        browser = QSplitter(Qt.Orientation.Vertical)
        self.browser = browser
        browser.setObjectName("historyBrowser")

        self.list_stack = QStackedWidget()
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Title", "Status", "Created"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(56)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(lambda _: self._emit_selected(self.load_requested))
        self.list_stack.addWidget(self.table)
        self.empty_label = QLabel(self.no_results_text)
        self.empty_label.setObjectName("emptyState")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.list_stack.addWidget(self.empty_label)
        browser.addWidget(self.list_stack)

        detail_panel = QFrame()
        self.detail_panel = detail_panel
        detail_panel.setObjectName("historyDetail")
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(18, 16, 18, 18)
        detail_layout.setSpacing(10)
        self.detail_eyebrow = QLabel("Selected recording")
        self.detail_eyebrow.setObjectName("eyebrow")
        self.detail_title = QLabel(self.no_selection_text)
        self.detail_title.setObjectName("detailTitle")
        self.detail_title.setWordWrap(True)
        self.detail_metadata = QLabel("")
        self.detail_metadata.setObjectName("fileMeta")
        self.detail_metadata.setWordWrap(True)
        detail_layout.addWidget(self.detail_eyebrow)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_metadata)

        self.preview_tabs = QTabWidget()
        self.transcript_preview = QPlainTextEdit()
        self.summary_preview = QPlainTextEdit()
        for preview in (self.transcript_preview, self.summary_preview):
            preview.setReadOnly(True)
            preview.setFrameStyle(QFrame.Shape.NoFrame)
        self.preview_tabs.addTab(self.transcript_preview, "Transcript")
        self.preview_tabs.addTab(self.summary_preview, "Summary")
        detail_layout.addWidget(self.preview_tabs, 1)

        player_row = QGridLayout()
        player_row.setHorizontalSpacing(8)
        player_row.setVerticalSpacing(6)
        self.play_button = QPushButton("Play")
        apply_icon(self.play_button, "play")
        self.play_text = "Play"
        self.pause_text = "Pause"
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_label = QLabel("00:00 / 00:00")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setMaximumWidth(82)
        self.volume_label = QLabel("Volume")
        player_row.addWidget(self.play_button, 0, 0)
        player_row.addWidget(self.position_slider, 0, 1)
        player_row.addWidget(self.time_label, 0, 2)
        player_row.addWidget(self.volume_label, 1, 0)
        player_row.addWidget(self.volume_slider, 1, 1, 1, 2)
        player_row.setColumnStretch(1, 1)
        detail_layout.addLayout(player_row)

        self.load_button = QPushButton("Load in workspace")
        self.load_button.setObjectName("primaryButton")
        apply_icon(self.load_button, "workspace_light")
        self.load_button.clicked.connect(
            lambda: self._emit_selected(self.load_requested)
        )
        browser.addWidget(detail_panel)
        browser.setStretchFactor(0, 4)
        browser.setStretchFactor(1, 3)
        browser.setSizes([430, 260])
        detail_panel.hide()
        layout.addWidget(browser, 1)

        primary_actions = QHBoxLayout()
        primary_actions.setSpacing(8)
        self.load_button.setParent(self)
        self.play_button.setParent(self)
        self.preview_button = QPushButton("Show preview")
        self.preview_button.setObjectName("compactButton")
        self.preview_button.setCheckable(True)
        apply_icon(self.preview_button, "summary")
        self.more_button = QToolButton()
        self.more_button.setObjectName("moreButton")
        self.more_button.setText("More actions")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QMenu(self.more_button)
        self.rename_action = self.more_menu.addAction("Rename")
        self.transcribe_action = self.more_menu.addAction("Retranscribe")
        self.summarize_action = self.more_menu.addAction("Generate summary")
        self.open_action = self.more_menu.addAction("Open folder")
        self.more_button.setMenu(self.more_menu)
        for action, signal in (
            (self.rename_action, self.rename_requested),
            (self.transcribe_action, self.transcribe_requested),
            (self.summarize_action, self.summarize_requested),
            (self.open_action, self.open_folder_requested),
        ):
            action.triggered.connect(
                lambda _checked=False, target=signal: self._emit_selected(target)
            )
        self.delete_button = QPushButton("Move to trash")
        self.delete_button.setObjectName("dangerButton")
        apply_icon(self.delete_button, "trash_danger")
        self.delete_button.clicked.connect(
            lambda: self._emit_selected(self.trash_requested)
        )
        primary_actions.addWidget(self.load_button)
        primary_actions.addWidget(self.play_button)
        primary_actions.addWidget(self.preview_button)
        primary_actions.addStretch()
        secondary_actions = QHBoxLayout()
        secondary_actions.setSpacing(8)
        secondary_actions.addStretch()
        secondary_actions.addWidget(self.more_button)
        secondary_actions.addWidget(self.delete_button)
        layout.addLayout(primary_actions)
        layout.addLayout(secondary_actions)

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.7)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.play_button.clicked.connect(self._toggle_playback)
        self.position_slider.sliderMoved.connect(self.player.setPosition)
        self.volume_slider.valueChanged.connect(
            lambda value: self.audio_output.setVolume(value / 100)
        )
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._playback_state_changed)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.clear_filters_button.clicked.connect(self.clear_filters)
        self.filter_toggle_button.toggled.connect(self.filter_panel.setVisible)
        self.preview_button.toggled.connect(self._toggle_preview)
        for widget in (
            self.search_edit,
            self.status_filter,
            self.source_filter,
            self.language_filter,
            self.sort_filter,
        ):
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.refresh)
            else:
                widget.currentIndexChanged.connect(self.refresh)
        self._set_actions_enabled(False)

    def refresh(self) -> None:
        selected = self.selected_id()
        self._records = self.service.search(
            self.search_edit.text(),
            status=self.status_filter.currentData() or None,
            source_type=self.source_filter.currentData() or None,
            language=self.language_filter.currentData() or None,
            sort=self.sort_filter.currentData() or "newest",
        )
        self.table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            values = (
                f"{record.title}\n{record.audio.filename}",
                self.status_texts.get(record.status, record.status),
                record.created_at[:16].replace("T", " "),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record.record_id)
                if column == 0:
                    item.setToolTip(record.audio.filename)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)
                if column == 1:
                    color = STATUS_COLORS.get(record.status, "#5f5e5b")
                    item.setForeground(QBrush(QColor(color)))
                self.table.setItem(row, column, item)
        self.result_count_label.setText(self.count_template.format(count=len(self._records)))
        self.update_compact_labels()
        self.empty_label.setText(self.no_results_text)
        self.list_stack.setCurrentWidget(self.table if self._records else self.empty_label)
        if self._records:
            restored_row = next(
                (
                    index
                    for index, record in enumerate(self._records)
                    if record.record_id == selected
                ),
                0,
            )
            self.table.selectRow(restored_row)
        else:
            self._clear_detail()

    def clear_filters(self) -> None:
        """Reset search and filters to the default newest-first view."""
        self.search_edit.clear()
        for combo in (
            self.status_filter,
            self.source_filter,
            self.language_filter,
            self.sort_filter,
        ):
            combo.setCurrentIndex(0)
        self.refresh()

    def update_compact_labels(self) -> None:
        """Refresh progressive-disclosure labels after filters or language change."""
        active_filters = sum(
            combo.currentIndex() > 0
            for combo in (
                self.status_filter,
                self.source_filter,
                self.language_filter,
                self.sort_filter,
            )
        )
        self.filter_toggle_button.setText(
            f"{self.filters_text} ({active_filters})"
            if active_filters
            else self.filters_text
        )
        self.preview_button.setText(
            self.hide_preview_text
            if self.preview_button.isChecked()
            else self.show_preview_text
        )
        self.more_button.setText(self.more_actions_text)
        if self.delete_button.isEnabled():
            self.delete_button.setText(self.move_to_trash_text)

    def set_trash_pending(self, pending: bool) -> None:
        """Show immediate feedback while Windows releases and moves the record."""
        self.delete_button.setText(
            self.moving_to_trash_text if pending else self.move_to_trash_text
        )
        self.delete_button.setEnabled(not pending and self.selected_id() is not None)

    def _toggle_preview(self, visible: bool) -> None:
        self.detail_panel.setVisible(visible)
        self.update_compact_labels()

    def selected_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._records):
            return None
        return self._records[row].record_id

    def stop_playback(self) -> None:
        """Stop playback and release the Windows media file handle."""
        self.player.stop()
        self.player.setSource(QUrl())

    def _emit_selected(self, signal: Signal) -> None:
        record_id = self.selected_id()
        if record_id:
            signal.emit(record_id)

    def _selection_changed(self) -> None:
        record_id = self.selected_id()
        if not record_id:
            self._clear_detail()
            return
        record = self._records[self.table.currentRow()]
        self.player.stop()
        self.player.setSource(
            QUrl.fromLocalFile(str(self.service.audio_path(record)))
            if record.audio.available
            else QUrl()
        )
        self.play_button.setEnabled(record.audio.available)
        self.position_slider.setEnabled(record.audio.available)
        self._set_actions_enabled(True)
        self.detail_title.setText(record.title)
        language = record.transcript.language if record.transcript else self.unavailable_text
        source = self.source_texts.get(record.source_type, record.source_type)
        created = record.created_at[:16].replace("T", " ")
        self.detail_metadata.setText(
            "\n".join(
                (
                    self.file_template.format(value=record.audio.filename),
                    self.source_template.format(value=source),
                    self.language_template.format(value=language or self.unavailable_text),
                    self.created_template.format(value=created),
                )
            )
        )
        self.transcript_preview.setPlainText(
            record.transcript.text if record.transcript else self.no_transcript_text
        )
        summary = ""
        if record.summary:
            summary = record.summary.markdown or record.summary.overview
        self.summary_preview.setPlainText(summary or self.no_summary_text)

    def _clear_detail(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())
        self.detail_title.setText(self.no_selection_text)
        self.detail_metadata.clear()
        self.transcript_preview.clear()
        self.summary_preview.clear()
        self.position_slider.setValue(0)
        self.preview_button.setChecked(False)
        self._set_actions_enabled(False)

    def _set_actions_enabled(self, enabled: bool) -> None:
        for button in (
            self.load_button,
            self.preview_button,
            self.delete_button,
        ):
            button.setEnabled(enabled)
        self.more_button.setEnabled(enabled)
        for action in (
            self.rename_action,
            self.transcribe_action,
            self.summarize_action,
            self.open_action,
        ):
            action.setEnabled(enabled)
        if not enabled:
            self.play_button.setEnabled(False)
            self.position_slider.setEnabled(False)

    def _toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _position_changed(self, position: int) -> None:
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        self.time_label.setText(
            f"{_format_ms(position)} / {_format_ms(self.player.duration())}"
        )

    def _duration_changed(self, duration: int) -> None:
        self.position_slider.setRange(0, duration)
        self._position_changed(self.player.position())

    def _playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText(
            self.pause_text
            if state == QMediaPlayer.PlaybackState.PlayingState
            else self.play_text
        )


class TrashPage(QWidget):
    """Application trash with explicit restoration and permanent deletion."""

    restore_requested = Signal(str)
    delete_requested = Signal(str)
    empty_requested = Signal()

    def __init__(self, service: LibraryService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self._records: list[LibraryRecord] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 36, 26)
        self.title_label = QLabel("Trash")
        self.title_label.setObjectName("pageTitle")
        layout.addWidget(self.title_label)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Title", "File", "Deleted record"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.restore_button = QPushButton("Restore")
        self.delete_button = QPushButton("Delete permanently")
        self.empty_button = QPushButton("Empty trash")
        self.delete_button.setObjectName("dangerButton")
        self.empty_button.setObjectName("dangerButton")
        apply_icon(self.restore_button, "history")
        apply_icon(self.delete_button, "trash")
        apply_icon(self.empty_button, "trash")
        self.restore_button.clicked.connect(
            lambda: self._emit_selected(self.restore_requested)
        )
        self.delete_button.clicked.connect(
            lambda: self._emit_selected(self.delete_requested)
        )
        self.empty_button.clicked.connect(self.empty_requested.emit)
        actions.addWidget(self.restore_button)
        actions.addWidget(self.delete_button)
        actions.addStretch()
        actions.addWidget(self.empty_button)
        layout.addLayout(actions)

    def refresh(self) -> None:
        self._records = self.service.list_records(trash=True)
        self.table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            for column, value in enumerate(
                (record.title, record.audio.filename, record.record_id)
            ):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def _emit_selected(self, signal: Signal) -> None:
        row = self.table.currentRow()
        if row >= 0:
            signal.emit(self._records[row].record_id)


def _format_ms(milliseconds: int) -> str:
    seconds = max(0, milliseconds // 1000)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
