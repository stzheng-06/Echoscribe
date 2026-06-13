from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.history import HistoryManager
from app.workers import TranscribeWorker, TranslateWorker


class HistoryWindow(QWidget):
    """Separate window for browsing history, playing audio, and re-processing."""

    def __init__(self, config: dict, history: HistoryManager, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("历史记录 - EchoScribe")
        self.setMinimumSize(900, 700)
        self.config = config
        self.history = history
        self.current_entry: dict | None = None

        # Audio player
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)

        self._build_ui()
        self._load_history()

    def _build_ui(self):
        self.setStyleSheet("background-color: #f5f5f5;")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Split view: list on left, details on right
        main_row = QHBoxLayout()
        main_row.setSpacing(16)

        # Left: history list
        list_container = QWidget()
        list_container.setStyleSheet("background-color: white; border-radius: 8px; color: #333333;")
        list_layout = QVBoxLayout(list_container)
        list_layout.setSpacing(12)
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.addWidget(QLabel("<h3>历史记录</h3>"))
        self.history_list = QListWidget()
        self.history_list.setMinimumWidth(300)
        self.history_list.setMinimumHeight(400)
        self.history_list.setStyleSheet("background-color: white; color: #333333;")
        self.history_list.itemClicked.connect(self._on_item_clicked)
        list_layout.addWidget(self.history_list)

        list_controls = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setStyleSheet("padding: 6px 12px;")
        self.refresh_btn.clicked.connect(self._load_history)
        self.delete_btn = QPushButton("删除")
        self.delete_btn.setStyleSheet("padding: 6px 12px;")
        self.delete_btn.clicked.connect(self._delete_current)
        list_controls.addWidget(self.refresh_btn)
        list_controls.addWidget(self.delete_btn)
        list_controls.addStretch()
        list_layout.addLayout(list_controls)

        main_row.addWidget(list_container, 1)

        # Right: details
        details_container = QWidget()
        details_container.setStyleSheet("background-color: white; border-radius: 8px; color: #333333;")
        details_layout = QVBoxLayout(details_container)
        details_layout.setSpacing(12)
        details_layout.setContentsMargins(12, 12, 12, 12)
        details_layout.addWidget(QLabel("<h3>详情</h3>"))

        self.info_label = QLabel("请选择一条历史记录")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("background-color: #fafafa; color: #333333; padding: 8px; border-radius: 4px;")
        details_layout.addWidget(self.info_label)

        # Audio playback controls
        audio_row = QHBoxLayout()
        self.play_btn = QPushButton("播放")
        self.play_btn.setEnabled(False)
        self.play_btn.setStyleSheet("padding: 8px 16px;")
        self.play_btn.clicked.connect(self._toggle_playback)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("padding: 8px 16px;")
        self.stop_btn.clicked.connect(self._stop_playback)
        audio_row.addWidget(self.play_btn)
        audio_row.addWidget(self.stop_btn)
        audio_row.addStretch()
        details_layout.addLayout(audio_row)

        # Transcription
        details_layout.addWidget(QLabel("转写:"))
        self.transcription_edit = QTextEdit()
        self.transcription_edit.setReadOnly(True)
        self.transcription_edit.setPlaceholderText("暂无转写")
        self.transcription_edit.setMinimumHeight(120)
        self.transcription_edit.setStyleSheet("background-color: #fafafa; color: #333333;")
        details_layout.addWidget(self.transcription_edit)

        # Translation
        details_layout.addWidget(QLabel("翻译:"))
        self.translation_edit = QTextEdit()
        self.translation_edit.setReadOnly(True)
        self.translation_edit.setPlaceholderText("暂无翻译")
        self.translation_edit.setMinimumHeight(120)
        self.translation_edit.setStyleSheet("background-color: #fafafa; color: #333333;")
        details_layout.addWidget(self.translation_edit)

        # Action buttons
        action_row = QHBoxLayout()
        self.retranscribe_btn = QPushButton("重新转写")
        self.retranscribe_btn.setEnabled(False)
        self.retranscribe_btn.setStyleSheet("padding: 8px 16px;")
        self.retranscribe_btn.clicked.connect(self._retranscribe)
        self.retranslate_btn = QPushButton("重新翻译")
        self.retranslate_btn.setEnabled(False)
        self.retranslate_btn.setStyleSheet("padding: 8px 16px;")
        self.retranslate_btn.clicked.connect(self._retranslate)
        self.save_text_btn = QPushButton("保存文本修改")
        self.save_text_btn.setEnabled(False)
        self.save_text_btn.setStyleSheet("padding: 8px 16px;")
        self.save_text_btn.clicked.connect(self._save_text_edits)
        action_row.addWidget(self.retranscribe_btn)
        action_row.addWidget(self.retranslate_btn)
        action_row.addWidget(self.save_text_btn)
        action_row.addStretch()
        details_layout.addLayout(action_row)

        main_row.addWidget(details_container, 2)
        layout.addLayout(main_row)

    def _load_history(self):
        """Load and display history entries."""
        self.history_list.clear()
        self.current_entry = None
        self._clear_details()
        entries = self.history.list_all()
        for entry in entries:
            text = self._entry_display_text(entry)
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, entry)
            self.history_list.addItem(item)

    def _entry_display_text(self, entry: dict) -> str:
        from datetime import datetime
        created = entry.get("created_at", "")
        if created:
            try:
                dt = datetime.fromisoformat(created)
                created = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        transcription = entry.get("transcription", "")
        if len(transcription) > 50:
            transcription = transcription[:50] + "..."
        return f"[{created}] {transcription}"

    def _clear_details(self):
        self.info_label.setText("请选择一条历史记录")
        self.transcription_edit.clear()
        self.translation_edit.clear()
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.retranscribe_btn.setEnabled(False)
        self.retranslate_btn.setEnabled(False)
        self.save_text_btn.setEnabled(False)
        self._stop_playback()

    def _on_item_clicked(self, item: QListWidgetItem):
        entry = item.data(Qt.UserRole)
        if not entry:
            return
        self.current_entry = entry
        self._show_entry(entry)

    def _show_entry(self, entry: dict):
        from datetime import datetime
        created = entry.get("created_at", "未知时间")
        if created:
            try:
                dt = datetime.fromisoformat(created)
                created = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        audio_path = entry.get("audio_path", "")
        path_exists = bool(audio_path) and Path(audio_path).exists()
        self.info_label.setText(
            f"创建时间: {created}\n音频文件: {audio_path or '无'}\n状态: {'文件存在' if path_exists else '文件不存在'}"
        )

        self.transcription_edit.setPlainText(entry.get("transcription", ""))
        self.translation_edit.setPlainText(entry.get("translation", ""))

        self.play_btn.setEnabled(path_exists)
        self.stop_btn.setEnabled(False)
        self.retranscribe_btn.setEnabled(path_exists)
        self.retranslate_btn.setEnabled(bool(entry.get("transcription")))
        self.save_text_btn.setEnabled(True)

        self._stop_playback()
        if path_exists:
            self.media_player.setSource(QUrl.fromLocalFile(str(audio_path)))

    def _toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _stop_playback(self):
        self.media_player.stop()

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setText("暂停")
            self.stop_btn.setEnabled(True)
        else:
            self.play_btn.setText("播放")
            self.stop_btn.setEnabled(state == QMediaPlayer.PausedState)

    def _delete_current(self):
        if not self.current_entry:
            QMessageBox.warning(self, "提示", "请先选择要删除的历史记录。")
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除这条历史记录吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        entry_id = self.current_entry.get("id")
        if entry_id:
            self.history.delete(entry_id)
            self._load_history()

    def _retranscribe(self):
        if not self.current_entry:
            return
        audio_path = self.current_entry.get("audio_path")
        if not audio_path or not Path(audio_path).exists():
            QMessageBox.warning(self, "提示", "音频文件不存在。")
            return
        api_key = self.config.get("api_key", "").strip()
        if not api_key:
            QMessageBox.warning(self, "提示", "请先填写 aihubmix API Key。")
            return

        self.retranscribe_btn.setEnabled(False)
        self.retranslate_btn.setEnabled(False)
        self._set_status("正在重新转写...")

        self.transcribe_worker = TranscribeWorker(
            Path(audio_path),
            api_key,
            self.config.get("base_url", "https://aihubmix.com/v1"),
            self.config.get("whisper_model", "whisper-1"),
        )
        self.transcribe_worker.finished.connect(self._on_retranscribe_finished)
        self.transcribe_worker.error.connect(self._on_retranscribe_error)
        self.transcribe_worker.start()

    def _on_retranscribe_finished(self, text: str):
        self.transcription_edit.setPlainText(text)
        self.translation_edit.clear()
        if self.current_entry:
            entry_id = self.current_entry.get("id")
            if entry_id:
                self.history.update(
                    entry_id, {"transcription": text, "translation": ""}
                )
                self.current_entry = self.history.get(entry_id)
                self._refresh_item_text()
        self._show_entry(self.current_entry)
        self._set_status("重新转写完成")

    def _on_retranscribe_error(self, message: str):
        self._set_status("重新转写失败")
        QMessageBox.critical(self, "转写失败", message)
        self._show_entry(self.current_entry)

    def _retranslate(self):
        if not self.current_entry:
            return
        text = self.transcription_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有转写文本可翻译。")
            return
        api_key = self.config.get("api_key", "").strip()
        if not api_key:
            QMessageBox.warning(self, "提示", "请先填写 aihubmix API Key。")
            return

        self.retranscribe_btn.setEnabled(False)
        self.retranslate_btn.setEnabled(False)
        self._set_status("正在重新翻译...")

        self.translate_worker = TranslateWorker(
            text,
            api_key,
            self.config.get("base_url", "https://aihubmix.com/v1"),
            self.config.get("translation_model", "deepseek-v4-flash"),
        )
        self.translate_worker.finished.connect(self._on_retranslate_finished)
        self.translate_worker.error.connect(self._on_retranslate_error)
        self.translate_worker.start()

    def _on_retranslate_finished(self, text: str):
        self.translation_edit.setPlainText(text)
        if self.current_entry:
            entry_id = self.current_entry.get("id")
            if entry_id:
                self.history.update(entry_id, {"translation": text})
                self.current_entry = self.history.get(entry_id)
                self._refresh_item_text()
        self._show_entry(self.current_entry)
        self._set_status("重新翻译完成")

    def _on_retranslate_error(self, message: str):
        self._set_status("重新翻译失败")
        QMessageBox.critical(self, "翻译失败", message)
        self._show_entry(self.current_entry)

    def _save_text_edits(self):
        if not self.current_entry:
            return
        entry_id = self.current_entry.get("id")
        if not entry_id:
            return
        updates = {
            "transcription": self.transcription_edit.toPlainText().strip(),
            "translation": self.translation_edit.toPlainText().strip(),
        }
        self.history.update(entry_id, updates)
        self.current_entry = self.history.get(entry_id)
        self._refresh_item_text()
        QMessageBox.information(self, "成功", "文本已保存。")

    def _refresh_item_text(self):
        item = self.history_list.currentItem()
        if item and self.current_entry:
            item.setText(self._entry_display_text(self.current_entry))
            item.setData(Qt.UserRole, self.current_entry)

    def _set_status(self, text: str):
        self.info_label.setText(text)

    def closeEvent(self, event):
        self.media_player.stop()
        event.accept()
