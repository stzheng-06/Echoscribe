"""Editable API and workspace settings dialog."""
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.config import (
    AppConfig,
    SUMMARY_LANGUAGES,
    SUMMARY_LENGTHS,
    SUMMARY_MODELS,
    save_config,
)
from app.exceptions import ConfigurationError
from app.i18n import UI_LANGUAGES, normalize_language, tr
from app.providers.openai_compatible_asr import OPENAI_COMPATIBLE_ASR_MODELS
from app.ui.fonts import register_application_fonts
from app.ui.icons import apply_icon, logo_icon
from app.ui.theme import APP_STYLESHEET


class SettingsDialog(QDialog):
    """Collect and persist cloud-provider and workspace settings."""

    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        register_application_fonts()
        self.config = config
        self.language = normalize_language(config.ui_language)
        self.setWindowTitle(tr(self.language, "settings_title"))
        self.setMinimumWidth(660)
        self.setStyleSheet(APP_STYLESHEET)

        self.api_key = QLineEdit(config.api_key)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.base_url = QLineEdit(config.base_url)
        self.transcription_model = QComboBox()
        self.transcription_model.setEditable(True)
        for model_id in dict.fromkeys(
            (config.transcription_model, *OPENAI_COMPATIBLE_ASR_MODELS)
        ):
            self.transcription_model.addItem(model_id, model_id)
        self.transcription_model.setCurrentText(config.transcription_model)
        self.summary_model = QComboBox()
        for model_id in SUMMARY_MODELS:
            self.summary_model.addItem(model_id, model_id)
        self.summary_model.setCurrentIndex(
            max(0, self.summary_model.findData(config.summary_model))
        )
        self.summary_language = QComboBox()
        for language_code, label in (
            ("zh-CN", "简体中文"),
            ("en", "English"),
            ("es", "Español"),
        ):
            if language_code in SUMMARY_LANGUAGES:
                self.summary_language.addItem(label, language_code)
        self.summary_language.setCurrentIndex(
            max(0, self.summary_language.findData(config.summary_language))
        )
        self.summary_length = QComboBox()
        for length in SUMMARY_LENGTHS:
            self.summary_length.addItem(
                tr(self.language, f"summary_length_{length}"), length
            )
        self.summary_length.setCurrentIndex(
            max(0, self.summary_length.findData(config.summary_length))
        )
        self.workspace_dir = QLineEdit(config.workspace_dir)
        self.browse_button = QPushButton(tr(self.language, "browse"))
        apply_icon(self.browse_button, "folder")
        self.browse_button.clicked.connect(self._browse_workspace)
        workspace_row = QHBoxLayout()
        workspace_row.addWidget(self.workspace_dir)
        workspace_row.addWidget(self.browse_button)

        self.chunk_minutes = QSpinBox()
        self.chunk_minutes.setRange(1, 10)
        self.chunk_minutes.setValue(config.local_chunk_minutes)
        self.copy_source = QCheckBox(tr(self.language, "copy_source"))
        self.copy_source.setChecked(True)
        self.copy_source.setEnabled(False)
        self.provider_chunking = QCheckBox(tr(self.language, "provider_chunking"))
        self.provider_chunking.setChecked(config.enable_provider_auto_chunking)
        self.ui_language = QComboBox()
        for code, label in UI_LANGUAGES.items():
            self.ui_language.addItem(label, code)
        self.ui_language.setCurrentIndex(
            max(0, self.ui_language.findData(self.language))
        )
        self.transcription_language = QComboBox()
        for key, code in (
            ("language_auto", "auto"),
            ("language_chinese", "zh"),
            ("language_spanish", "es"),
        ):
            self.transcription_language.addItem(tr(self.language, key), code)
        self.transcription_language.setCurrentIndex(
            max(0, self.transcription_language.findData(config.transcription_language))
        )

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
        form.addRow(tr(self.language, "api_key"), self.api_key)
        form.addRow(tr(self.language, "base_url"), self.base_url)
        form.addRow(tr(self.language, "transcription_model"), self.transcription_model)
        form.addRow(tr(self.language, "summary_model"), self.summary_model)
        form.addRow(tr(self.language, "summary_language"), self.summary_language)
        form.addRow(tr(self.language, "summary_length"), self.summary_length)
        form.addRow(tr(self.language, "interface_language"), self.ui_language)
        form.addRow(tr(self.language, "transcription_language"), self.transcription_language)
        form.addRow(tr(self.language, "workspace_directory"), workspace_row)
        form.addRow(tr(self.language, "local_chunk_minutes"), self.chunk_minutes)
        form.addRow("", self.provider_chunking)
        form.addRow("", self.copy_source)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_button:
            save_button.setText(tr(self.language, "save"))
            save_button.setObjectName("primaryButton")
            apply_icon(save_button, "save_light")
        if cancel_button:
            cancel_button.setText(tr(self.language, "cancel"))
            apply_icon(cancel_button, "cancel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        title_row = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(logo_icon().pixmap(30, 30))
        mark.setFixedSize(32, 32)
        title = QLabel(tr(self.language, "settings_title"))
        title.setObjectName("pageTitle")
        title_row.addWidget(mark)
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)
        layout.addLayout(form)
        layout.addWidget(buttons)

        label_keys = (
            "api_key", "base_url", "transcription_model", "summary_model",
            "summary_language", "summary_length", "interface_language", "transcription_language",
            "workspace_directory", "local_chunk_minutes",
        )
        longest_label = max(
            self.fontMetrics().horizontalAdvance(tr(self.language, key))
            for key in label_keys
        )
        longest_option = max(
            self.provider_chunking.sizeHint().width(), self.copy_source.sizeHint().width()
        )
        self.setMinimumWidth(max(660, min(900, longest_label + longest_option + 112)))

    def _browse_workspace(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, tr(self.language, "select_workspace"), self.workspace_dir.text()
        )
        if selected:
            self.workspace_dir.setText(selected)

    def accept(self) -> None:
        base_url = self.base_url.text().strip()
        model = self.transcription_model.currentText().strip()
        workspace = self.workspace_dir.text().strip()
        if not base_url or not model or not workspace:
            self._show_message(
                QMessageBox.Icon.Warning,
                tr(self.language, "invalid_settings"),
                tr(self.language, "invalid_settings_body"),
            )
            return

        self.config.api_key = self.api_key.text().strip()
        self.config.base_url = base_url
        self.config.transcription_model = model
        self.config.summary_model = str(self.summary_model.currentData())
        self.config.summary_language = str(self.summary_language.currentData())
        self.config.summary_length = str(self.summary_length.currentData())
        self.config.ui_language = str(self.ui_language.currentData())
        self.config.transcription_language = str(self.transcription_language.currentData())
        self.config.workspace_dir = str(Path(workspace).expanduser())
        self.config.local_chunk_minutes = self.chunk_minutes.value()
        self.config.enable_provider_auto_chunking = self.provider_chunking.isChecked()
        self.config.copy_source_audio = True
        try:
            save_config(self.config)
        except ConfigurationError as exc:
            self._show_message(
                QMessageBox.Icon.Critical, tr(self.language, "settings_error"), str(exc)
            )
            return
        super().accept()

    def _show_message(self, icon: QMessageBox.Icon, title: str, message: str) -> None:
        box = QMessageBox(icon, title, message, QMessageBox.StandardButton.Ok, self)
        ok_button = box.button(QMessageBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText(tr(self.language, "ok"))
        box.exec()
