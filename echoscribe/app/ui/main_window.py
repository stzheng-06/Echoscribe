"""Main EchoScribe desktop window."""
from __future__ import annotations

import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QEvent, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QInputDialog,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.audio.probe import probe_audio, recommended_mode
from app.audio.duplex_capture import DuplexAudioRecorder
from app.config import (
    SUMMARY_LANGUAGES,
    SUMMARY_LENGTHS,
    SUMMARY_MODELS,
    load_config,
    save_config,
)
from app.exceptions import (
    AudioValidationError,
    ConfigurationError,
    EchoScribeError,
    ProviderAudioDurationError,
)
from app.i18n import normalize_language, tr
from app.models import (
    AudioMetadata, JobState, LibraryRecord, MeetingSummary, TranscriptionResult,
    TranslationVersion,
)
from app.providers.openai_compatible_asr import (
    OPENAI_COMPATIBLE_ASR_MODELS,
    OPENAI_COMPATIBLE_MAX_DURATION_SECONDS,
    OpenAICompatibleASRProvider,
)
from app.providers.openai_compatible_llm import OpenAICompatibleLLMProvider
from app.services.job_service import JobService
from app.services.pdf_export import export_summary_pdf
from app.services.summarization_service import SummarizationService
from app.services.transcription_service import (
    TranscriptionService,
    requires_local_chunking,
    select_transcription_model,
)
from app.services.translation_service import SUPPORTED_TRANSLATIONS, TranslationService
from app.storage.library import LibraryService
from app.storage.workspace import atomic_write_text
from app.ui.fonts import register_application_fonts
from app.ui.floating_recorder import FloatingRecorderWidget, RecordingLevelBridge
from app.ui.icons import apply_icon, logo_icon
from app.ui.library_page import LibraryPage, TrashPage
from app.ui.settings_dialog import SettingsDialog
from app.ui.theme import APP_STYLESHEET
from app.workers.task_runner import CancellationToken, TaskRunner

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        register_application_fonts()
        self.setWindowTitle("EchoScribe")
        self.setWindowIcon(logo_icon())
        self.setMinimumSize(980, 700)

        self._config = load_config()
        self._language = normalize_language(self._config.ui_language)
        self._library = LibraryService(Path(self._config.workspace_dir))
        self._record_id: str | None = None
        self._pending_trash_id: str | None = None
        self._trash_moves_pending: set[str] = set()
        self._selected_file: Path | None = None
        self._metadata: AudioMetadata | None = None
        self._job_state: JobState | None = None
        self._job_dir: Path | None = None
        self._runner: TaskRunner | None = None
        self._task_kind = ""
        self._thread_pool = QThreadPool.globalInstance()
        self._record_stop = threading.Event()
        self._active_recorder: DuplexAudioRecorder | None = None
        self._recording_active = False
        self._record_clock = QElapsedTimer()
        self._record_timer = QTimer(self)
        self._record_timer.setInterval(500)
        self._record_timer.timeout.connect(self._update_recording_status)
        self._level_bridge = RecordingLevelBridge(self)
        self._build_ui()
        self._floating_recorder = FloatingRecorderWidget()
        self._floating_recorder.restore_requested.connect(self._restore_from_floating)
        self._floating_recorder.stop_requested.connect(self._stop_from_floating)
        self._level_bridge.level_changed.connect(self._floating_recorder.set_level)
        self._retranslate_ui()
        self._start_legacy_migration()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._sidebar = QFrame()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(16, 22, 16, 18)
        sidebar_layout.setSpacing(6)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(9)
        self._logo_label = QLabel()
        self._logo_label.setObjectName("brandMark")
        self._logo_label.setPixmap(logo_icon().pixmap(30, 30))
        self._logo_label.setFixedSize(32, 32)
        self._brand_label = QLabel()
        self._brand_label.setObjectName("brand")
        self._tagline_label = QLabel()
        self._tagline_label.setObjectName("tagline")
        self._tagline_label.setWordWrap(True)
        brand_row.addWidget(self._logo_label)
        brand_row.addWidget(self._brand_label, 1)
        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addWidget(self._tagline_label)
        sidebar_layout.addSpacing(24)

        self._workspace_nav = QPushButton()
        self._workspace_nav.setProperty("active", True)
        self._history_nav = QPushButton()
        self._trash_nav = QPushButton()
        for button, icon_name in (
            (self._workspace_nav, "workspace"),
            (self._history_nav, "history"),
            (self._trash_nav, "trash"),
        ):
            button.setProperty("nav", True)
            apply_icon(button, icon_name)
        self._workspace_nav.clicked.connect(lambda: self._show_page(0))
        self._history_nav.clicked.connect(lambda: self._show_page(1))
        self._trash_nav.clicked.connect(lambda: self._show_page(2))
        sidebar_layout.addWidget(self._workspace_nav)
        sidebar_layout.addWidget(self._history_nav)
        sidebar_layout.addWidget(self._trash_nav)
        sidebar_layout.addSpacing(18)

        self._import_button = QPushButton()
        apply_icon(self._import_button, "import")
        self._import_button.clicked.connect(self._import_audio)
        self._record_button = QPushButton()
        apply_icon(self._record_button, "record")
        self._record_button.clicked.connect(self._toggle_recording)
        self._floating_button = QPushButton()
        apply_icon(self._floating_button, "floating")
        self._floating_button.setObjectName("floatingButton")
        self._floating_button.setEnabled(False)
        self._floating_button.clicked.connect(self._enter_floating_mode)
        self._settings_button = QPushButton()
        apply_icon(self._settings_button, "settings")
        self._settings_button.clicked.connect(self._open_settings)
        self._open_folder_button = QPushButton()
        apply_icon(self._open_folder_button, "folder")
        self._open_folder_button.setEnabled(False)
        self._open_folder_button.clicked.connect(self._open_output_folder)
        sidebar_layout.addWidget(self._import_button)
        sidebar_layout.addWidget(self._record_button)
        sidebar_layout.addWidget(self._floating_button)
        sidebar_layout.addWidget(self._settings_button)
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(self._open_folder_button)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(34, 28, 36, 26)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        self._page_title = QLabel()
        self._page_title.setObjectName("pageTitle")
        self._status_label = QLabel()
        self._status_label.setObjectName("status")
        self._status_label.setWordWrap(True)
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        header_row.addWidget(self._page_title)
        header_row.addStretch()
        header_row.addWidget(self._status_label)

        file_panel = QFrame()
        file_panel.setObjectName("filePanel")
        file_layout = QVBoxLayout(file_panel)
        file_layout.setContentsMargins(16, 13, 16, 14)
        file_layout.setSpacing(3)
        self._file_label = QLabel()
        self._file_label.setWordWrap(True)
        self._file_label.setObjectName("sectionTitle")
        self._file_meta = QLabel()
        self._file_meta.setObjectName("fileMeta")
        self._file_meta.setWordWrap(True)
        file_layout.addWidget(self._file_label)
        file_layout.addWidget(self._file_meta)

        self._mode_selector = QComboBox()
        self._mode_selector.setMinimumWidth(124)
        self._mode_label = QLabel()
        self._mode_label.setObjectName("eyebrow")
        self._asr_model_label = QLabel()
        self._asr_model_label.setObjectName("eyebrow")
        self._asr_model_selector = QComboBox()
        self._asr_model_selector.setMinimumWidth(220)
        self._asr_language_label = QLabel()
        self._asr_language_label.setObjectName("eyebrow")
        self._asr_language_selector = QComboBox()
        self._asr_language_selector.setMinimumWidth(124)
        self._transcribe_button = QPushButton()
        apply_icon(self._transcribe_button, "transcribe_light")
        self._transcribe_button.setObjectName("primaryButton")
        self._transcribe_button.setEnabled(False)
        self._transcribe_button.clicked.connect(self._start_transcription)
        self._cancel_button = QPushButton()
        apply_icon(self._cancel_button, "cancel")
        self._cancel_button.setObjectName("dangerButton")
        self._cancel_button.setEnabled(False)
        self._cancel_button.setVisible(False)
        self._cancel_button.clicked.connect(self._cancel_transcription)
        header_row.addWidget(self._cancel_button)

        self._transcription_settings_panel = QFrame()
        self._transcription_settings_panel.setObjectName("settingsPanel")
        transcription_settings = QHBoxLayout(self._transcription_settings_panel)
        transcription_settings.setContentsMargins(16, 12, 16, 14)
        transcription_settings.setSpacing(12)
        for label, selector, stretch in (
            (self._asr_model_label, self._asr_model_selector, 3),
            (self._asr_language_label, self._asr_language_selector, 2),
            (self._mode_label, self._mode_selector, 2),
        ):
            field = QVBoxLayout()
            field.setSpacing(5)
            field.addWidget(label)
            field.addWidget(selector)
            transcription_settings.addLayout(field, stretch)
        transcription_settings.addWidget(
            self._transcribe_button, 0, Qt.AlignmentFlag.AlignBottom
        )

        self._summary_button = QPushButton()
        apply_icon(self._summary_button, "summary")
        self._summary_button.setObjectName("summaryButton")
        self._summary_button.setEnabled(False)
        self._summary_button.clicked.connect(self._start_summary)
        self._summary_generation_language = QComboBox()
        self._summary_generation_language.setMinimumWidth(112)
        self._summary_model_selector = QComboBox()
        self._summary_model_selector.setMinimumWidth(150)
        self._summary_length_selector = QComboBox()
        self._summary_length_selector.setMinimumWidth(82)
        self._summary_generation_label = QLabel()
        self._summary_generation_label.setObjectName("eyebrow")
        self._summary_model_label = QLabel()
        self._summary_model_label.setObjectName("eyebrow")
        self._summary_length_label = QLabel()
        self._summary_length_label.setObjectName("eyebrow")

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)

        self._text_area = QTextEdit()
        self._text_area.setReadOnly(True)
        self._summary_area = QTextEdit()
        self._summary_area.setReadOnly(True)
        self._summary_area.setObjectName("summaryDocument")
        self._summary_area.document().setDocumentMargin(18)
        self._summary_area.document().setDefaultStyleSheet(
            "h1 { font-size: 24px; margin: 8px 0 18px 0; }"
            "h2 { font-size: 17px; margin: 22px 0 9px 0; }"
            "p { margin: 0 0 12px 0; line-height: 1.55; }"
            "li { margin-bottom: 7px; line-height: 1.5; }"
        )
        self._copy_button = QPushButton()
        apply_icon(self._copy_button, "copy")
        self._copy_button.setEnabled(False)
        self._copy_button.clicked.connect(self._copy_transcript)
        self._export_transcript_button = QPushButton()
        self._export_transcript_button.setObjectName("exportButton")
        apply_icon(self._export_transcript_button, "export")
        self._export_transcript_button.setEnabled(False)
        self._export_transcript_button.clicked.connect(
            lambda: self._export_current_content("transcript")
        )
        self._transcript_title = QLabel()
        self._transcript_title.setObjectName("sectionTitle")
        self._summary_title = QLabel()
        self._summary_title.setObjectName("sectionTitle")

        transcript_pane = QWidget()
        transcript_layout = QVBoxLayout(transcript_pane)
        transcript_layout.setContentsMargins(0, 6, 18, 0)
        transcript_layout.setSpacing(2)
        transcript_layout.addWidget(self._transcript_title)
        transcript_tools = QHBoxLayout()
        self._transcript_language = QComboBox()
        self._translate_transcript_button = QPushButton()
        self._translate_transcript_button.setObjectName("translationButton")
        apply_icon(self._translate_transcript_button, "translate")
        self._translate_transcript_button.setEnabled(False)
        self._transcript_language.currentIndexChanged.connect(self._render_selected_versions)
        self._translate_transcript_button.clicked.connect(
            lambda: self._start_translation("transcript")
        )
        transcript_tools.addWidget(self._transcript_language)
        transcript_tools.addWidget(self._translate_transcript_button)
        transcript_tools.addStretch()
        transcript_layout.addLayout(transcript_tools)
        transcript_layout.addWidget(self._text_area)
        transcript_footer = QHBoxLayout()
        transcript_footer.setSpacing(8)
        transcript_footer.addWidget(self._copy_button)
        transcript_footer.addWidget(self._export_transcript_button)
        transcript_footer.addStretch()
        transcript_layout.addLayout(transcript_footer)
        self._summary_entry_button = QPushButton()
        self._summary_entry_button.setObjectName("summaryEntry")
        self._summary_entry_button.clicked.connect(self._show_summary_page)
        transcript_layout.addWidget(self._summary_entry_button)
        summary_pane = QWidget()
        summary_layout = QVBoxLayout(summary_pane)
        summary_layout.setContentsMargins(0, 6, 0, 0)
        summary_layout.setSpacing(8)
        summary_header = QHBoxLayout()
        self._back_to_transcript_button = QPushButton()
        self._back_to_transcript_button.setObjectName("compactButton")
        self._back_to_transcript_button.clicked.connect(self._show_transcript_page)
        summary_header.addWidget(self._back_to_transcript_button)
        summary_header.addWidget(self._summary_title)
        summary_header.addStretch()
        summary_layout.addLayout(summary_header)

        self._summary_settings_panel = QFrame()
        self._summary_settings_panel.setObjectName("settingsPanel")
        summary_settings = QHBoxLayout(self._summary_settings_panel)
        summary_settings.setContentsMargins(16, 12, 16, 14)
        summary_settings.setSpacing(12)
        for label, selector, stretch in (
            (self._summary_generation_label, self._summary_generation_language, 2),
            (self._summary_model_label, self._summary_model_selector, 3),
            (self._summary_length_label, self._summary_length_selector, 2),
        ):
            field = QVBoxLayout()
            field.setSpacing(5)
            field.addWidget(label)
            field.addWidget(selector)
            summary_settings.addLayout(field, stretch)
        summary_settings.addWidget(
            self._summary_button, 0, Qt.AlignmentFlag.AlignBottom
        )
        summary_layout.addWidget(self._summary_settings_panel)

        summary_tools = QHBoxLayout()
        self._summary_language = QComboBox()
        self._translate_summary_button = QPushButton()
        self._translate_summary_button.setObjectName("translationButton")
        apply_icon(self._translate_summary_button, "translate")
        self._translate_summary_button.setEnabled(False)
        self._summary_language.currentIndexChanged.connect(self._render_selected_versions)
        self._translate_summary_button.clicked.connect(
            lambda: self._start_translation("summary")
        )
        summary_tools.addWidget(self._summary_language)
        summary_tools.addWidget(self._translate_summary_button)
        summary_tools.addStretch()
        summary_layout.addLayout(summary_tools)
        summary_layout.addWidget(self._summary_area)
        self._export_summary_button = QToolButton()
        self._export_summary_button.setObjectName("exportButton")
        apply_icon(self._export_summary_button, "export")
        self._export_summary_button.setEnabled(False)
        self._summary_export_menu = QMenu(self._export_summary_button)
        self._export_pdf_action = QAction(self._summary_export_menu)
        self._export_markdown_action = QAction(self._summary_export_menu)
        self._export_pdf_action.setIcon(self._export_summary_button.icon())
        self._export_pdf_action.triggered.connect(self._export_current_summary_pdf)
        self._export_markdown_action.triggered.connect(
            lambda: self._export_current_content("summary")
        )
        self._summary_export_menu.addAction(self._export_pdf_action)
        self._summary_export_menu.addAction(self._export_markdown_action)
        self._export_summary_button.setMenu(self._summary_export_menu)
        self._export_summary_button.setDefaultAction(self._export_pdf_action)
        self._export_summary_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.MenuButtonPopup
        )
        self._export_summary_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        summary_footer = QHBoxLayout()
        summary_footer.addWidget(self._export_summary_button)
        summary_footer.addStretch()
        summary_layout.addLayout(summary_footer)
        self._workspace_stack = QStackedWidget()
        self._workspace_stack.addWidget(transcript_pane)
        self._workspace_stack.addWidget(summary_pane)

        layout.addLayout(header_row)
        layout.addWidget(file_panel)
        layout.addWidget(self._transcription_settings_panel)
        layout.addWidget(self._progress)
        layout.addWidget(self._workspace_stack, 1)
        self._pages = QStackedWidget()
        self._pages.addWidget(content)
        self._history_page = LibraryPage(self._library)
        self._trash_page = TrashPage(self._library)
        self._pages.addWidget(self._history_page)
        self._pages.addWidget(self._trash_page)
        self._connect_library_actions()
        root.addWidget(self._sidebar)
        root.addWidget(self._pages, 1)
        self.setCentralWidget(central)
        self.setStyleSheet(APP_STYLESHEET)

    def _t(self, key: str, **values) -> str:
        return tr(self._language, key, **values)

    def _retranslate_ui(self) -> None:
        """Apply the selected language to all persistent window chrome."""
        self.setWindowTitle(self._t("app_name"))
        self._brand_label.setText(self._t("app_name"))
        self._tagline_label.setText(self._t("tagline"))
        self._page_title.setText(self._t("workspace"))
        self._workspace_nav.setText(self._t("workspace"))
        self._history_nav.setText(self._t("history"))
        self._trash_nav.setText(self._t("trash"))
        self._import_button.setText(self._t("import_audio"))
        self._record_button.setText(
            self._t("stop_recording")
            if self._task_kind == "recording"
            else self._t("capture_pc_audio")
        )
        self._floating_button.setText(self._t("shrink_to_bubble"))
        self._floating_recorder.set_texts(
            restore=self._t("restore_main_window"),
            stop=self._t("stop_recording"),
            recording=self._t("recording_floating"),
        )
        self._settings_button.setText(self._t("settings"))
        self._open_folder_button.setText(self._t("open_output_folder"))
        self._mode_label.setText(self._t("mode"))
        self._asr_model_label.setText(self._t("model"))
        self._asr_language_label.setText(self._t("transcription_language"))
        self._transcription_settings_panel.setAccessibleName(
            self._t("transcription_settings")
        )
        self._summary_settings_panel.setAccessibleName(self._t("summary_settings"))
        current_mode = self._mode_selector.currentData() or self._config.default_mode
        self._mode_selector.clear()
        for mode in ("auto", "quick", "meeting"):
            self._mode_selector.addItem(self._t(f"mode_{mode}"), mode)
        index = self._mode_selector.findData(current_mode)
        self._mode_selector.setCurrentIndex(max(0, index))
        self._refresh_workspace_models()
        self._refresh_summary_generation_controls()
        current_asr_language = (
            self._asr_language_selector.currentData() or self._config.transcription_language
        )
        self._asr_language_selector.clear()
        for key, code in (("language_auto", "auto"), ("language_chinese", "zh"), ("language_spanish", "es")):
            self._asr_language_selector.addItem(self._t(key), code)
        self._asr_language_selector.setCurrentIndex(
            max(0, self._asr_language_selector.findData(current_asr_language))
        )
        self._transcribe_button.setText(self._t("transcribe"))
        self._summary_button.setText(self._t("generate_summary"))
        self._summary_generation_language.setToolTip(
            self._t("summary_generation_language")
        )
        self._summary_generation_label.setText(
            self._t("summary_generation_language")
        )
        self._summary_model_label.setText(self._t("summary_model"))
        self._summary_length_label.setText(self._t("summary_length"))
        self._summary_model_selector.setToolTip(self._t("summary_model"))
        self._summary_length_selector.setToolTip(self._t("summary_length"))
        self._cancel_button.setText(self._t("cancel"))
        self._transcript_title.setText(self._t("transcript"))
        self._summary_title.setText(self._t("summary"))
        self._summary_entry_button.setText(f"{self._t('open_summary')}  ›")
        self._back_to_transcript_button.setText(
            f"‹  {self._t('back_to_transcript')}"
        )
        self._text_area.setPlaceholderText(self._t("transcript_placeholder"))
        self._summary_area.setPlaceholderText(self._t("summary_placeholder"))
        self._copy_button.setText(self._t("copy_transcript"))
        self._translate_transcript_button.setText(
            self._t("translate_transcript_action")
        )
        self._translate_summary_button.setText(self._t("translate_summary_action"))
        self._export_transcript_button.setText(self._t("export_current"))
        self._export_summary_button.setText(self._t("export_pdf"))
        self._export_pdf_action.setText(self._t("export_pdf"))
        self._export_markdown_action.setText(self._t("export_markdown"))
        for selector in (self._transcript_language, self._summary_language):
            current = selector.currentData() or "original"
            selector.blockSignals(True)
            selector.clear()
            selector.addItem(self._t("original"), "original")
            selector.addItem("English", "en")
            selector.addItem("简体中文", "zh-CN")
            selector.addItem("Español", "es")
            selector.setCurrentIndex(max(0, selector.findData(current)))
            selector.blockSignals(False)
        self._history_page.title_label.setText(self._t("history"))
        self._trash_page.title_label.setText(self._t("trash"))
        history = self._history_page
        history.search_edit.setPlaceholderText(self._t("search_history"))
        history.table.setHorizontalHeaderLabels([
            self._t("record_title"), self._t("status"), self._t("created"),
        ])
        history.clear_filters_button.setText(self._t("clear_filters"))
        history.filters_text = self._t("filters")
        history.show_preview_text = self._t("show_preview")
        history.hide_preview_text = self._t("hide_preview")
        history.more_actions_text = self._t("more_actions")
        history.move_to_trash_text = self._t("move_to_trash")
        history.moving_to_trash_text = self._t("moving_to_trash")
        history.detail_eyebrow.setText(self._t("history_selected"))
        history.preview_tabs.setTabText(0, self._t("transcript"))
        history.preview_tabs.setTabText(1, self._t("summary"))
        history.count_template = self._t("history_count", count="{count}")
        history.no_results_text = self._t("history_no_results")
        history.no_selection_text = self._t("history_no_selection")
        history.no_transcript_text = self._t("history_no_transcript")
        history.no_summary_text = self._t("history_no_summary")
        history.file_template = f"{self._t('file')}: {{value}}"
        history.source_template = f"{self._t('source')}: {{value}}"
        history.language_template = f"{self._t('language')}: {{value}}"
        history.created_template = f"{self._t('created')}: {{value}}"
        history.unavailable_text = self._t("unavailable")
        history.status_texts = {
            value: self._t(f"status_{value}")
            for value in (
                "created", "transcribing", "summarizing", "completed", "failed", "cancelled"
            )
        }
        history.source_texts = {
            "import": self._t("source_import"),
            "pc_recording": self._t("source_recording"),
        }
        history.play_text = self._t("play")
        history.pause_text = self._t("pause")
        history.play_button.setText(history.play_text)
        history.volume_label.setText(self._t("volume"))
        history.load_button.setText(self._t("load_workspace"))
        history.rename_action.setText(self._t("rename"))
        history.transcribe_action.setText(self._t("retranscribe"))
        history.summarize_action.setText(self._t("regenerate_summary"))
        history.open_action.setText(self._t("open_output_folder"))
        history.delete_button.setText(history.move_to_trash_text)
        history.update_compact_labels()
        trash = self._trash_page
        trash.table.setHorizontalHeaderLabels([
            self._t("record_title"), self._t("file"), self._t("record_id")
        ])
        trash.restore_button.setText(self._t("restore"))
        trash.delete_button.setText(self._t("delete_permanently"))
        trash.empty_button.setText(self._t("empty_trash"))
        self._replace_combo(history.status_filter, [
            (self._t("all_statuses"), ""), (self._t("status_created"), "created"),
            (self._t("status_transcribing"), "transcribing"),
            (self._t("status_summarizing"), "summarizing"),
            (self._t("status_completed"), "completed"),
            (self._t("status_failed"), "failed"), (self._t("status_cancelled"), "cancelled"),
        ])
        self._replace_combo(history.source_filter, [
            (self._t("all_sources"), ""), (self._t("source_import"), "import"),
            (self._t("source_recording"), "pc_recording"),
        ])
        self._replace_combo(history.language_filter, [
            (self._t("all_languages"), ""), ("English", "en"),
            ("简体中文", "zh-CN"), ("Español", "es"),
        ])
        self._replace_combo(history.sort_filter, [
            (self._t("sort_newest"), "newest"), (self._t("sort_oldest"), "oldest"),
            (self._t("sort_title"), "title"),
        ])
        history.refresh()
        if self._runner is None:
            self._status_label.setText(
                self._t("ready_to_transcribe") if self._selected_file else self._t("ready")
            )
        self._render_file_metadata()
        self._fit_translated_controls()

    def _fit_translated_controls(self) -> None:
        """Size non-wrapping controls from the active translation without clipping."""
        sidebar_buttons = (
            self._workspace_nav,
            self._history_nav,
            self._trash_nav,
            self._import_button,
            self._record_button,
            self._floating_button,
            self._settings_button,
            self._open_folder_button,
        )
        required_sidebar = max(button.sizeHint().width() for button in sidebar_buttons) + 34
        self._sidebar.setFixedWidth(max(220, min(292, required_sidebar)))

        mode_width = max(
            self._mode_selector.fontMetrics().horizontalAdvance(
                self._mode_selector.itemText(index)
            )
            for index in range(self._mode_selector.count())
        ) + 48
        self._mode_selector.setMinimumWidth(max(124, mode_width))

    def _show_page(self, index: int) -> None:
        self._pages.setCurrentIndex(index)
        for button, button_index in (
            (self._workspace_nav, 0),
            (self._history_nav, 1),
            (self._trash_nav, 2),
        ):
            button.setProperty("active", button_index == index)
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 1:
            self._history_page.refresh()
        elif index == 2:
            self._trash_page.refresh()

    def _show_summary_page(self) -> None:
        self._transcription_settings_panel.setVisible(False)
        self._workspace_stack.setCurrentIndex(1)

    def _show_transcript_page(self) -> None:
        self._transcription_settings_panel.setVisible(True)
        self._workspace_stack.setCurrentIndex(0)

    @staticmethod
    def _replace_combo(combo: QComboBox, items: list[tuple[str, str]]) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for label, value in items:
            combo.addItem(label, value)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        combo.blockSignals(False)

    def _start_legacy_migration(self) -> None:
        """Run the retry-safe legacy scan without blocking application startup."""
        runner = TaskRunner(lambda _token: self._library.migrate_legacy())
        runner.signals.result.connect(lambda _ids: self._history_page.refresh())
        runner.signals.error.connect(
            lambda error, trace: logger.error("Library migration failed: %s\n%s", error, trace)
        )
        self._migration_runner = runner
        self._thread_pool.start(runner)

    def _connect_library_actions(self) -> None:
        page = self._history_page
        page.load_requested.connect(self._load_record)
        page.rename_requested.connect(self._rename_record)
        page.transcribe_requested.connect(self._retranscribe_record)
        page.summarize_requested.connect(self._summarize_record)
        page.open_folder_requested.connect(self._open_record_folder)
        page.trash_requested.connect(self._trash_record)
        self._trash_page.restore_requested.connect(self._restore_record)
        self._trash_page.delete_requested.connect(self._delete_record_permanently)
        self._trash_page.empty_requested.connect(self._empty_trash)

    def _render_file_metadata(self) -> None:
        if self._metadata is None:
            self._file_label.setText(self._t("no_file"))
            self._file_meta.setText(self._t("empty_hint"))
            return
        duration = (
            self._t("duration_seconds", seconds=self._metadata.duration_seconds)
            if self._metadata.duration_seconds is not None
            else self._t("duration_unknown")
        )
        recommended = recommended_mode(self._metadata)
        recommendation = (
            self._t("recommended", mode=self._t(f"mode_{recommended}"))
            if recommended
            else ""
        )
        self._file_label.setText(self._t("selected", filename=self._metadata.filename))
        self._file_meta.setText(
            self._t("duration", duration=duration, recommendation=recommendation)
        )

    def _import_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("select_audio"),
            "",
            f"{self._t('audio_files')} (*.wav *.mp3 *.m4a *.mp4 *.webm *.ogg *.flac)",
        )
        if not path:
            return
        try:
            metadata = probe_audio(Path(path))
            record = self._library.create_record(
                Path(metadata.path), source_type="import", title=metadata.filename
            )
            metadata = probe_audio(self._library.audio_path(record))
        except AudioValidationError as exc:
            self._selected_file = None
            self._metadata = None
            self._transcribe_button.setEnabled(False)
            self._show_message(QMessageBox.Icon.Warning, self._t("invalid_audio"), str(exc))
            return
        except OSError as exc:
            self._show_message(QMessageBox.Icon.Critical, self._t("job_creation_failed"), str(exc))
            return

        self._selected_file = Path(metadata.path)
        self._metadata = metadata
        self._record_id = record.record_id
        self._job_state = record.job
        self._job_dir = self._library.record_dir(record.record_id)
        self._show_transcript_page()
        self._transcript_language.setCurrentIndex(0)
        self._summary_language.setCurrentIndex(0)
        self._text_area.clear()
        self._summary_area.clear()
        self._summary_button.setEnabled(False)
        self._update_content_actions(record)
        self._render_file_metadata()
        self._transcribe_button.setEnabled(True)
        self._status_label.setText(self._t("ready_to_transcribe"))
        self._history_page.refresh()
        logger.info(
            "Selected audio file: %s (%s bytes, duration=%s)",
            metadata.path,
            metadata.size_bytes,
            metadata.duration_seconds,
        )

    def _toggle_recording(self) -> None:
        if self._task_kind == "recording":
            self._stop_recording()
        elif self._runner is None:
            self._start_recording()

    def _start_recording(self) -> None:
        self._config = load_config()
        title = datetime.now().strftime("PC recording %Y-%m-%d %H:%M:%S")
        try:
            record = self._library.create_empty_record(
                source_type="pc_recording", title=title, extension=".wav"
            )
        except OSError as exc:
            self._show_message(QMessageBox.Icon.Critical, self._t("recording_failed"), str(exc))
            return
        self._record_id = record.record_id
        self._job_dir = self._library.record_dir(record.record_id)
        output_path = self._library.audio_path(record)
        recorder = DuplexAudioRecorder()
        self._active_recorder = recorder
        self._record_stop = threading.Event()

        def capture(token: CancellationToken) -> Path:
            return recorder.record(
                output_path,
                is_stopped=lambda: self._record_stop.is_set() or token.is_cancelled,
                on_level=self._level_bridge.level_changed.emit,
            )

        runner = TaskRunner(capture)
        runner.signals.started.connect(self._on_recording_started)
        runner.signals.result.connect(self._on_recording_result)
        runner.signals.error.connect(self._on_task_error)
        runner.signals.cancelled.connect(self._on_task_cancelled)
        runner.signals.finished.connect(self._on_task_finished)
        self._runner = runner
        self._task_kind = "recording"
        self._thread_pool.start(runner)

    def _stop_recording(self) -> None:
        self._recording_active = False
        self._record_stop.set()
        if self._active_recorder is not None:
            self._active_recorder.request_stop()
        self._record_button.setEnabled(False)
        self._floating_button.setEnabled(False)
        self._status_label.setText(self._t("finalizing_recording"))

    def _on_recording_started(self) -> None:
        self._recording_active = True
        self._record_clock.start()
        self._record_timer.start()
        self._import_button.setEnabled(False)
        self._settings_button.setEnabled(False)
        self._record_button.setText(self._t("stop_recording"))
        self._record_button.setEnabled(True)
        self._floating_button.setEnabled(True)
        self._floating_recorder.reset()
        self._transcribe_button.setEnabled(False)
        self._summary_button.setEnabled(False)
        self._cancel_button.setEnabled(False)
        self._cancel_button.setVisible(False)
        self._progress.setRange(0, 0)
        self._update_recording_status()
        # Recording is designed to stay out of the way by default.
        QTimer.singleShot(150, self._enter_floating_mode)

    def _update_recording_status(self) -> None:
        if self._task_kind == "recording" and self._record_clock.isValid():
            seconds = max(0, self._record_clock.elapsed() // 1000)
            self._status_label.setText(self._t("recording_elapsed", seconds=seconds))
            self._floating_recorder.set_elapsed_seconds(seconds)

    def _enter_floating_mode(self) -> None:
        if not self._recording_active:
            return
        self._floating_recorder.show_near(self)
        self.hide()

    def _restore_from_floating(self) -> None:
        self._floating_recorder.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _stop_from_floating(self) -> None:
        if not self._recording_active:
            return
        self._floating_recorder.stop_button.setEnabled(False)
        self._restore_from_floating()
        self._stop_recording()

    def _on_recording_result(self, path: Path) -> None:
        if self._record_id is None:
            return
        record = self._library.finalize_audio(self._record_id)
        metadata = probe_audio(self._library.audio_path(record))
        self._selected_file = Path(metadata.path)
        self._metadata = metadata
        self._job_state = None
        self._job_dir = self._library.record_dir(record.record_id)
        self._show_transcript_page()
        self._text_area.clear()
        self._summary_area.clear()
        self._copy_button.setEnabled(False)
        self._summary_button.setEnabled(False)
        self._open_folder_button.setEnabled(False)
        self._update_content_actions(record)
        self._render_file_metadata()
        self._status_label.setText(self._t("recording_ready"))

    def _selected_mode(self) -> str:
        selected = str(self._mode_selector.currentData() or "auto")
        if selected != "auto":
            return selected
        recommendation = recommended_mode(self._metadata) if self._metadata else None
        return recommendation or "quick"

    def _refresh_workspace_models(self) -> None:
        current_model = self._asr_model_selector.currentData()
        self._asr_model_selector.blockSignals(True)
        self._asr_model_selector.clear()
        api_models = dict.fromkeys(
            (self._config.transcription_model, *OPENAI_COMPATIBLE_ASR_MODELS)
        )
        for model_id in api_models:
            self._asr_model_selector.addItem(model_id, model_id)
        selected = self._asr_model_selector.findData(current_model)
        if selected < 0:
            selected = self._asr_model_selector.findData(
                self._config.transcription_model
            )
        self._asr_model_selector.setCurrentIndex(max(0, selected))
        self._asr_model_selector.blockSignals(False)

    def _refresh_summary_generation_controls(self) -> None:
        """Translate summary options without losing the current selections."""
        current_language = (
            self._summary_generation_language.currentData()
            or self._config.summary_language
        )
        current_model = (
            self._summary_model_selector.currentData() or self._config.summary_model
        )
        current_length = (
            self._summary_length_selector.currentData() or self._config.summary_length
        )
        language_labels = {
            "zh-CN": "简体中文",
            "en": "English",
            "es": "Español",
        }
        self._summary_generation_language.clear()
        for language in SUMMARY_LANGUAGES:
            self._summary_generation_language.addItem(
                language_labels[language], language
            )
        self._summary_generation_language.setCurrentIndex(
            max(0, self._summary_generation_language.findData(current_language))
        )
        self._summary_model_selector.clear()
        for model_id in SUMMARY_MODELS:
            self._summary_model_selector.addItem(model_id, model_id)
        self._summary_model_selector.setCurrentIndex(
            max(0, self._summary_model_selector.findData(current_model))
        )
        self._summary_length_selector.clear()
        for length in SUMMARY_LENGTHS:
            self._summary_length_selector.addItem(
                self._t(f"summary_length_{length}"), length
            )
        self._summary_length_selector.setCurrentIndex(
            max(0, self._summary_length_selector.findData(current_length))
        )

    def _start_transcription(self) -> None:
        if self._selected_file is None or self._runner is not None:
            return
        self._config = load_config()
        provider_name = "openai-compatible"
        model = str(
            self._asr_model_selector.currentData()
            or self._config.transcription_model
        )
        model = select_transcription_model(
            model, self._metadata.duration_seconds if self._metadata else None
        )
        requested_language = str(self._asr_language_selector.currentData() or "auto")
        if not self._config.api_key.strip():
            self._show_message(
                QMessageBox.Icon.Warning,
                self._t("api_key_required"),
                self._t(
                    "api_key_required_body", action=self._t("action_transcribing")
                ),
            )
            self._open_settings()
            return

        mode = self._selected_mode()
        job_service = JobService(
            Path(self._config.workspace_dir), library_service=self._library
        )
        strategy = (
            "local_chunks"
            if requires_local_chunking(
                self._metadata.duration_seconds if self._metadata else None,
                self._config.enable_provider_auto_chunking,
                OPENAI_COMPATIBLE_MAX_DURATION_SECONDS,
            )
            else "direct"
        )
        try:
            resumable = (
                job_service.find_resumable_job(self._selected_file)
                if strategy == "local_chunks"
                else None
            )
            resume = False
            if resumable:
                resume = self._ask_yes_no(
                    self._t("resume_transcription"),
                    self._t(
                        "resume_body", count=len(resumable[0].completed_chunk_ids)
                    ),
                )
            if resume and resumable:
                state, job_dir = resumable
            else:
                state, job_dir = job_service.create_job(
                    self._selected_file,
                    mode=mode,
                    provider=provider_name,
                    model=model,
                    requested_language=requested_language,
                    strategy=strategy,
                    copy_source_audio=True,
                )
        except (EchoScribeError, OSError) as exc:
            self._show_message(
                QMessageBox.Icon.Critical, self._t("job_creation_failed"), str(exc)
            )
            return

        self._job_state = state
        self._record_id = state.job_id
        self._job_dir = job_dir
        self._summary_area.clear()
        self._summary_button.setEnabled(False)
        try:
            job_service.transition(state, "transcribing")
        except (EchoScribeError, OSError) as exc:
            self._show_message(
                QMessageBox.Icon.Critical, self._t("job_state_error"), str(exc)
            )
            return

        def transcribe(token: CancellationToken) -> TranscriptionResult:
            if token.is_cancelled:
                return TranscriptionResult(text="")
            provider = OpenAICompatibleASRProvider(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
                enable_auto_chunking=self._config.enable_provider_auto_chunking,
            )
            service = TranscriptionService(
                provider, library_service=self._library, record_id=state.job_id
            )
            try:
                result = service.transcribe(
                    Path(state.source_audio),
                    model=state.model,
                    diarize=(
                        mode == "meeting"
                        and provider.supports_model_diarization(state.model)
                    ),
                    language=None if requested_language == "auto" else requested_language,
                    job_dir=job_dir,
                    chunk_minutes=self._config.local_chunk_minutes,
                    overlap_seconds=self._config.local_chunk_overlap_seconds,
                    completed_chunk_ids=state.completed_chunk_ids,
                    on_chunk_completed=lambda chunk_id: job_service.mark_chunk_completed(
                        state, chunk_id
                    ),
                    on_chunk_failed=lambda chunk_id, error: job_service.mark_chunk_failed(
                        state, chunk_id, error
                    ),
                    is_cancelled=lambda: token.is_cancelled,
                )
            except Exception as exc:
                if token.is_cancelled:
                    return TranscriptionResult(text="")
                job_service.transition(state, "failed", error_message=str(exc))
                raise
            if not token.is_cancelled:
                try:
                    job_service.transition(state, "completed")
                except EchoScribeError:
                    if not token.is_cancelled:
                        raise
            return result

        runner = TaskRunner(transcribe)
        runner.signals.started.connect(self._on_task_started)
        runner.signals.result.connect(self._on_transcription_result)
        runner.signals.error.connect(self._on_task_error)
        runner.signals.cancelled.connect(self._on_task_cancelled)
        runner.signals.finished.connect(self._on_task_finished)
        self._runner = runner
        self._task_kind = "transcription"
        self._thread_pool.start(runner)

    def _start_summary(self) -> None:
        transcript = ""
        if self._record_id:
            record = self._library.load(self._record_id)
            transcript = record.transcript.text.strip() if record.transcript else ""
        if not transcript or self._record_id is None or self._job_dir is None or self._runner:
            return
        self._config = load_config()
        if not self._persist_summary_generation_defaults():
            return

        if self._job_state is None:
            now = datetime.now().astimezone().isoformat()
            self._job_state = JobState(
                job_id=self._record_id,
                mode="meeting",
                status="completed",
                source_audio=str(self._selected_file or ""),
                provider="openai-compatible",
                model=self._config.transcription_model,
                strategy="direct",
                created_at=now,
                updated_at=now,
            )
            self._library.save_job(self._job_state)
        if not self._config.api_key.strip():
            self._show_message(
                QMessageBox.Icon.Warning,
                self._t("api_key_required"),
                self._t(
                    "api_key_required_body", action=self._t("action_summarizing")
                ),
            )
            self._open_settings()
            return
        if not self._config.summary_model.strip():
            self._show_message(
                QMessageBox.Icon.Warning,
                self._t("summary_model_required"),
                self._t("summary_model_required_body"),
            )
            self._open_settings()
            return

        state = self._job_state
        job_dir = self._job_dir
        job_service = JobService(
            Path(self._config.workspace_dir), library_service=self._library
        )
        try:
            job_service.transition(state, "summarizing")
        except (EchoScribeError, OSError) as exc:
            self._show_message(
                QMessageBox.Icon.Critical, self._t("job_state_error"), str(exc)
            )
            return

        def summarize(token: CancellationToken) -> MeetingSummary:
            if token.is_cancelled:
                return MeetingSummary()
            provider = OpenAICompatibleLLMProvider(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
            )
            service = SummarizationService(
                provider, library_service=self._library, record_id=state.job_id
            )
            try:
                result = service.summarize(
                    transcript,
                    model=self._config.summary_model,
                    language=self._config.summary_language,
                    length=self._config.summary_length,
                    job_dir=job_dir,
                )
            except Exception as exc:
                if token.is_cancelled:
                    return MeetingSummary()
                job_service.transition(state, "failed", error_message=str(exc))
                raise
            if not token.is_cancelled:
                try:
                    job_service.transition(state, "completed")
                except EchoScribeError:
                    if not token.is_cancelled:
                        raise
            return result

        runner = TaskRunner(summarize)
        runner.signals.started.connect(self._on_task_started)
        runner.signals.result.connect(self._on_summary_result)
        runner.signals.error.connect(self._on_task_error)
        runner.signals.cancelled.connect(self._on_task_cancelled)
        runner.signals.finished.connect(self._on_task_finished)
        self._runner = runner
        self._task_kind = "summary"
        self._show_summary_page()
        self._thread_pool.start(runner)

    def _persist_summary_generation_defaults(self) -> bool:
        """Save the visible summary choices as the defaults for future runs."""
        self._config.summary_language = str(
            self._summary_generation_language.currentData()
        )
        self._config.summary_model = str(self._summary_model_selector.currentData())
        self._config.summary_length = str(self._summary_length_selector.currentData())
        try:
            save_config(self._config)
        except ConfigurationError as exc:
            self._show_message(
                QMessageBox.Icon.Critical, self._t("settings_error"), str(exc)
            )
            return False
        return True

    def _cancel_transcription(self) -> None:
        if self._runner is None:
            return
        if self._task_kind == "recording":
            self._recording_active = False
            self._record_stop.set()
            if self._active_recorder is not None:
                self._active_recorder.request_stop()
        self._runner.cancel()
        if self._job_state and self._job_state.status in {
            "created",
            "transcribing",
            "summarizing",
        }:
            try:
                JobService(
                    Path(self._config.workspace_dir), library_service=self._library
                ).transition(
                    self._job_state, "cancelled"
                )
            except EchoScribeError:
                logger.exception("Could not persist job cancellation")
        self._cancel_button.setEnabled(False)
        self._status_label.setText(self._t("cancelling"))

    def _on_task_started(self) -> None:
        self._import_button.setEnabled(False)
        self._record_button.setEnabled(False)
        self._floating_button.setEnabled(False)
        self._settings_button.setEnabled(False)
        self._transcribe_button.setEnabled(False)
        self._summary_button.setEnabled(False)
        self._summary_generation_language.setEnabled(False)
        self._summary_model_selector.setEnabled(False)
        self._summary_length_selector.setEnabled(False)
        self._cancel_button.setEnabled(True)
        self._cancel_button.setVisible(True)
        self._update_content_actions()
        self._progress.setRange(0, 0)
        if self._task_kind.startswith("translation"):
            key = "translating_background"
        else:
            key = "summarizing_background" if self._task_kind == "summary" else "transcribing_background"
        self._status_label.setText(self._t(key))

    def _on_transcription_result(self, result: TranscriptionResult) -> None:
        self._transcript_language.setCurrentIndex(0)
        self._text_area.setPlainText(result.text)
        self._copy_button.setEnabled(bool(result.text))
        self._summary_button.setEnabled(bool(result.text))
        self._open_folder_button.setEnabled(self._job_dir is not None)
        self._status_label.setText(self._t("transcription_completed"))
        self._update_content_actions()
        self._history_page.refresh()

    def _on_summary_result(self, result: MeetingSummary) -> None:
        self._summary_language.setCurrentIndex(0)
        self._summary_area.setMarkdown(result.markdown)
        self._open_folder_button.setEnabled(self._job_dir is not None)
        self._status_label.setText(self._t("summary_completed"))
        self._update_content_actions()
        self._history_page.refresh()

    def _start_translation(self, kind: str) -> None:
        if self._runner is not None or self._record_id is None:
            return
        selector = self._transcript_language if kind == "transcript" else self._summary_language
        target = str(selector.currentData() or "original")
        if target == "original":
            return
        record = self._library.load(self._record_id)
        existing = (
            record.transcript_translations if kind == "transcript"
            else record.summary_translations
        )
        if target in existing and not self._ask_yes_no(
            self._t("retranslate"), self._t("retranslate_confirm")
        ):
            self._render_selected_versions()
            return
        source = record.transcript if kind == "transcript" else record.summary
        if source is None:
            return
        self._config = load_config()
        if not self._config.api_key.strip() or not self._config.summary_model.strip():
            self._show_message(
                QMessageBox.Icon.Warning,
                self._t("api_key_required"),
                self._t("api_key_required_body", action=self._t("action_translating")),
            )
            return

        def translate(token: CancellationToken) -> tuple[str, TranslationVersion]:
            provider = OpenAICompatibleLLMProvider(
                api_key=self._config.api_key, base_url=self._config.base_url
            )
            service = TranslationService(provider)
            if kind == "transcript":
                version = service.translate_transcript(
                    source,
                    target_language=target,
                    model=self._config.summary_model,
                    is_cancelled=lambda: token.is_cancelled,
                )
            else:
                version = service.translate_summary(
                    source,
                    target_language=target,
                    model=self._config.summary_model,
                    is_cancelled=lambda: token.is_cancelled,
                )
            if token.is_cancelled:
                return kind, version
            self._library.save_translation(self._record_id, kind, version)
            return kind, version

        runner = TaskRunner(translate)
        runner.signals.started.connect(self._on_task_started)
        runner.signals.result.connect(self._on_translation_result)
        runner.signals.error.connect(self._on_task_error)
        runner.signals.cancelled.connect(self._on_task_cancelled)
        runner.signals.finished.connect(self._on_task_finished)
        self._runner = runner
        self._task_kind = f"translation_{kind}"
        self._thread_pool.start(runner)

    def _on_translation_result(self, result: tuple[str, TranslationVersion]) -> None:
        self._render_selected_versions()
        self._status_label.setText(self._t("translation_completed"))
        self._history_page.refresh()

    def _render_selected_versions(self) -> None:
        if not self._record_id:
            self._update_content_actions()
            return
        try:
            record = self._library.load(self._record_id)
        except ValueError:
            self._update_content_actions()
            return
        transcript_language = self._transcript_language.currentData()
        if transcript_language == "original":
            self._text_area.setPlainText(record.transcript.text if record.transcript else "")
        else:
            version = record.transcript_translations.get(str(transcript_language))
            self._text_area.setPlainText(version.text if version else "")
        summary_language = self._summary_language.currentData()
        if summary_language == "original":
            markdown = record.summary.markdown if record.summary else ""
        else:
            version = record.summary_translations.get(str(summary_language))
            markdown = version.summary.markdown if version and version.summary else ""
        self._summary_area.setMarkdown(markdown)
        self._update_content_actions(record)

    def _selected_content(
        self, kind: str, record: LibraryRecord | None = None
    ) -> tuple[str, str, LibraryRecord | None]:
        """Return the exact original or translated content selected in the UI."""
        if self._record_id is None:
            return "", "original", None
        try:
            record = record or self._library.load(self._record_id)
        except ValueError:
            return "", "original", None
        selector = (
            self._transcript_language if kind == "transcript" else self._summary_language
        )
        language = str(selector.currentData() or "original")
        if kind == "transcript":
            if language == "original":
                text = record.transcript.text if record.transcript else ""
            else:
                version = record.transcript_translations.get(language)
                text = version.text if version else ""
        elif language == "original":
            text = ""
            if record.summary:
                text = record.summary.markdown or record.summary.overview
        else:
            version = record.summary_translations.get(language)
            text = ""
            if version and version.summary:
                text = version.summary.markdown or version.summary.overview
        return text, language, record

    def _update_content_actions(self, record: LibraryRecord | None = None) -> None:
        """Keep translate, copy, and export actions aligned with visible content."""
        transcript, transcript_language, record = self._selected_content(
            "transcript", record
        )
        summary, summary_language, record = self._selected_content("summary", record)
        busy = self._runner is not None
        has_transcript_source = bool(record and record.transcript and record.transcript.text)
        has_summary_source = bool(record and record.summary)
        self._copy_button.setEnabled(bool(transcript))
        self._export_transcript_button.setEnabled(bool(transcript))
        self._export_summary_button.setEnabled(bool(summary))
        self._translate_transcript_button.setEnabled(
            has_transcript_source and transcript_language != "original" and not busy
        )
        self._translate_summary_button.setEnabled(
            has_summary_source and summary_language != "original" and not busy
        )
        self._summary_button.setText(
            self._t("regenerate_summary") if has_summary_source
            else self._t("generate_summary")
        )

    def _selected_summary(
        self, record: LibraryRecord | None = None
    ) -> tuple[MeetingSummary | None, str, LibraryRecord | None]:
        """Return the exact summary object currently displayed in the summary page."""
        if self._record_id is None:
            return None, "original", None
        try:
            record = record or self._library.load(self._record_id)
        except ValueError:
            return None, "original", None
        selection = str(self._summary_language.currentData() or "original")
        if selection == "original":
            summary = record.summary
            language = (
                summary.language if summary and summary.language
                else record.transcript.language if record.transcript and record.transcript.language
                else "original"
            )
            return summary, language, record
        version = record.summary_translations.get(selection)
        return (version.summary if version else None), selection, record

    def _export_current_summary_pdf(self) -> None:
        """Export the visible original or translated summary as a formal PDF."""
        summary, language, record = self._selected_summary()
        if summary is None or record is None or not (summary.markdown or summary.overview):
            return
        safe_title = _safe_export_stem(record.title)
        default_path = Path(self._config.workspace_dir) / (
            f"{safe_title}-summary-{language}.pdf"
        )
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            self._t("export_summary_pdf_title"),
            str(default_path),
            f"{self._t('pdf_files')} (*.pdf)",
        )
        if not selected_path:
            return
        destination = Path(selected_path)
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")
        try:
            export_summary_pdf(
                destination,
                summary,
                record_title=record.title,
                source_file=record.audio.filename,
            )
        except (OSError, RuntimeError) as exc:
            logger.exception("Could not export summary PDF")
            self._show_message(
                QMessageBox.Icon.Critical, self._t("export_failed"), str(exc)
            )
            return
        self._status_label.setText(self._t("export_succeeded", path=str(destination)))

    def _export_current_content(self, kind: str) -> None:
        """Export the currently selected original or translated content."""
        text, language, record = self._selected_content(kind)
        if not text or record is None:
            return
        if kind == "summary":
            _summary, language, _record = self._selected_summary(record)
        extension = ".txt" if kind == "transcript" else ".md"
        safe_title = _safe_export_stem(record.title)
        filename = f"{safe_title}-{kind}-{language}{extension}"
        default_path = Path(self._config.workspace_dir) / filename
        title_key = (
            "export_transcript_title" if kind == "transcript" else "export_summary_title"
        )
        file_filter = (
            f"{self._t('text_files')} (*.txt)"
            if kind == "transcript"
            else f"{self._t('markdown_files')} (*.md)"
        )
        selected_path, _ = QFileDialog.getSaveFileName(
            self, self._t(title_key), str(default_path), file_filter
        )
        if not selected_path:
            return
        destination = Path(selected_path)
        if destination.suffix.lower() != extension:
            destination = destination.with_suffix(extension)
        try:
            atomic_write_text(destination, text.rstrip() + "\n")
        except OSError as exc:
            logger.exception("Could not export %s", kind)
            self._show_message(
                QMessageBox.Icon.Critical, self._t("export_failed"), str(exc)
            )
            return
        self._status_label.setText(
            self._t("export_succeeded", path=str(destination))
        )

    def _load_record(self, record_id: str) -> None:
        if self._runner is not None:
            return
        record = self._library.load(record_id)
        self._record_id = record_id
        self._job_state = record.job
        self._job_dir = self._library.record_dir(record_id)
        self._show_transcript_page()
        self._selected_file = self._library.audio_path(record) if record.audio.available else None
        self._metadata = AudioMetadata(
            path=str(self._selected_file or ""),
            filename=record.audio.filename,
            extension=record.audio.extension,
            size_bytes=record.audio.size_bytes,
            duration_seconds=record.audio.duration_seconds,
            sample_rate=record.audio.sample_rate,
            channels=record.audio.channels,
        )
        self._transcript_language.setCurrentIndex(0)
        self._summary_language.setCurrentIndex(0)
        self._render_selected_versions()
        self._copy_button.setEnabled(bool(record.transcript and record.transcript.text))
        self._summary_button.setEnabled(bool(record.transcript and record.transcript.text))
        self._transcribe_button.setEnabled(record.audio.available)
        self._open_folder_button.setEnabled(True)
        self._render_file_metadata()
        if not record.audio.available:
            self._file_meta.setText(self._t("audio_unavailable"))
        self._show_page(0)

    def _rename_record(self, record_id: str) -> None:
        record = self._library.load(record_id)
        title, accepted = QInputDialog.getText(
            self, self._t("rename"), self._t("record_title"), text=record.title
        )
        if accepted and title.strip():
            self._library.rename(record_id, title)
            self._history_page.refresh()

    def _retranscribe_record(self, record_id: str) -> None:
        self._load_record(record_id)
        self._start_transcription()

    def _summarize_record(self, record_id: str) -> None:
        self._load_record(record_id)
        self._start_summary()

    def _open_record_folder(self, record_id: str) -> None:
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self._library.record_dir(record_id)))
        )

    def _trash_record(self, record_id: str) -> None:
        if self._runner is not None and self._record_id == record_id:
            self._pending_trash_id = record_id
            self._cancel_transcription()
            return
        if record_id in self._trash_moves_pending:
            return
        self._history_page.stop_playback()
        self._trash_moves_pending.add(record_id)
        self._history_page.set_trash_pending(True)
        QTimer.singleShot(0, lambda: self._finish_trash_record(record_id, 10))

    def _finish_trash_record(self, record_id: str, retries: int) -> None:
        """Move a record after Qt releases its Windows media file handle."""
        try:
            self._library.move_to_trash(record_id)
        except PermissionError as exc:
            if retries > 0 and getattr(exc, "winerror", None) in {5, 32}:
                QTimer.singleShot(
                    100,
                    lambda: self._finish_trash_record(record_id, retries - 1),
                )
                return
            self._trash_moves_pending.discard(record_id)
            self._history_page.set_trash_pending(False)
            logger.exception("Could not move library record %s to trash", record_id)
            self._show_message(
                QMessageBox.Icon.Critical,
                self._t("library_action_failed"),
                str(exc),
            )
            return
        except Exception as exc:
            self._trash_moves_pending.discard(record_id)
            self._history_page.set_trash_pending(False)
            logger.exception("Could not move library record %s to trash", record_id)
            self._show_message(
                QMessageBox.Icon.Critical,
                self._t("library_action_failed"),
                str(exc),
            )
            return
        self._trash_moves_pending.discard(record_id)
        self._history_page.set_trash_pending(False)
        if self._record_id == record_id:
            self._clear_workspace_record()
        self._history_page.refresh()
        self._trash_page.refresh()

    def _restore_record(self, record_id: str) -> None:
        self._library.restore(record_id)
        self._trash_page.refresh()
        self._history_page.refresh()

    def _delete_record_permanently(self, record_id: str) -> None:
        if self._ask_yes_no(self._t("delete_permanently"), self._t("delete_confirm")):
            self._library.permanently_delete(record_id)
            self._trash_page.refresh()

    def _empty_trash(self) -> None:
        if self._ask_yes_no(self._t("empty_trash"), self._t("empty_trash_confirm")):
            self._library.empty_trash()
            self._trash_page.refresh()

    def _clear_workspace_record(self) -> None:
        self._record_id = None
        self._job_state = None
        self._job_dir = None
        self._selected_file = None
        self._metadata = None
        self._show_transcript_page()
        self._text_area.clear()
        self._summary_area.clear()
        self._update_content_actions()
        self._render_file_metadata()

    def _on_task_error(self, error: Exception, traceback_text: str) -> None:
        if self._task_kind == "recording":
            if self._floating_recorder.isVisible():
                self._restore_from_floating()
            key = "recording_failed"
        elif self._task_kind.startswith("translation"):
            key = "translation_failed"
        else:
            key = "summary_failed" if self._task_kind == "summary" else "transcription_failed"
        message = str(error)
        if isinstance(error, ProviderAudioDurationError):
            key = "audio_too_long_title"
            message = self._t("audio_too_long_body")
        logger.error("%s:\n%s", self._t(key), traceback_text)
        self._status_label.setText(self._t(key))
        self._show_message(QMessageBox.Icon.Critical, self._t(key), message)

    def _on_task_cancelled(self) -> None:
        if self._task_kind == "recording":
            if self._floating_recorder.isVisible():
                self._restore_from_floating()
            key = "recording_failed"
        elif self._task_kind.startswith("translation"):
            key = "translation_cancelled"
        else:
            key = "summary_cancelled" if self._task_kind == "summary" else "transcription_cancelled"
        self._status_label.setText(self._t(key))

    def _on_task_finished(self) -> None:
        was_recording = self._task_kind == "recording"
        self._recording_active = False
        self._record_timer.stop()
        self._floating_recorder.hide()
        self._floating_recorder.reset()
        self._active_recorder = None
        self._progress.setRange(0, 100)
        self._progress.setValue(100 if self._job_state and self._job_state.status == "completed" else 0)
        self._cancel_button.setEnabled(False)
        self._cancel_button.setVisible(False)
        self._transcribe_button.setEnabled(self._selected_file is not None)
        original_transcript = ""
        if self._record_id:
            try:
                record = self._library.load(self._record_id)
                original_transcript = record.transcript.text if record.transcript else ""
            except ValueError:
                pass
        self._summary_button.setEnabled(bool(original_transcript))
        self._summary_generation_language.setEnabled(True)
        self._summary_model_selector.setEnabled(True)
        self._summary_length_selector.setEnabled(True)
        self._import_button.setEnabled(True)
        self._settings_button.setEnabled(True)
        self._record_button.setEnabled(True)
        self._floating_button.setEnabled(False)
        self._record_button.setText(self._t("capture_pc_audio"))
        self._runner = None
        self._task_kind = ""
        self._update_content_actions()
        pending_trash = self._pending_trash_id
        self._pending_trash_id = None
        if pending_trash and self._library.record_dir(pending_trash).exists():
            self._history_page.stop_playback()
            self._library.move_to_trash(pending_trash)
            if self._record_id == pending_trash:
                self._clear_workspace_record()
            self._history_page.refresh()
            self._trash_page.refresh()
        if was_recording and self._selected_file is not None:
            self._transcribe_button.setEnabled(True)

    def _copy_transcript(self) -> None:
        QGuiApplication.clipboard().setText(self._text_area.toPlainText())
        self._status_label.setText(self._t("transcript_copied"))

    def _open_output_folder(self) -> None:
        if self._job_dir is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._job_dir)))

    def _open_settings(self) -> None:
        previous_workspace = Path(self._config.workspace_dir).expanduser().resolve()
        dialog = SettingsDialog(self._config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._config = dialog.config
            current_workspace = Path(self._config.workspace_dir).expanduser().resolve()
            if current_workspace != previous_workspace:
                self._library = LibraryService(current_workspace)
                self._history_page.service = self._library
                self._trash_page.service = self._library
                self._clear_workspace_record()
                self._start_legacy_migration()
            self._language = normalize_language(self._config.ui_language)
            self._summary_generation_language.setCurrentIndex(
                max(
                    0,
                    self._summary_generation_language.findData(
                        self._config.summary_language
                    ),
                )
            )
            self._summary_model_selector.setCurrentIndex(
                max(
                    0,
                    self._summary_model_selector.findData(self._config.summary_model),
                )
            )
            self._summary_length_selector.setCurrentIndex(
                max(
                    0,
                    self._summary_length_selector.findData(
                        self._config.summary_length
                    ),
                )
            )
            self._retranslate_ui()
            self._status_label.setText(self._t("settings_saved"))

    def _show_message(self, icon: QMessageBox.Icon, title: str, message: str) -> None:
        box = QMessageBox(icon, title, message, QMessageBox.StandardButton.Ok, self)
        ok_button = box.button(QMessageBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText(self._t("ok"))
        box.exec()

    def _ask_yes_no(self, title: str, message: str) -> bool:
        box = QMessageBox(
            QMessageBox.Icon.Question,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            self,
        )
        yes_button = box.button(QMessageBox.StandardButton.Yes)
        no_button = box.button(QMessageBox.StandardButton.No)
        if yes_button:
            yes_button.setText(self._t("yes"))
        if no_button:
            no_button.setText(self._t("no"))
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        return box.exec() == QMessageBox.StandardButton.Yes

    def closeEvent(self, event: QCloseEvent) -> None:
        """Persist cooperative cancellation when the window closes mid-task."""
        self._floating_recorder.hide()
        if self._runner is not None:
            self._cancel_transcription()
        event.accept()

    def changeEvent(self, event: QEvent) -> None:
        """Turn a recording-time minimize action into compact floating mode."""
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and self._recording_active
        ):
            QTimer.singleShot(0, self._enter_floating_mode)


def _safe_export_stem(title: str) -> str:
    """Return a short Windows-safe filename stem for user exports."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    return (safe or "EchoScribe")[:80]
