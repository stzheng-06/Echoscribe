import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QBrush
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.audio_tools import AudioDevice
from app.recorder import (
    AudioRecorder,
    get_default_microphone_device,
    get_default_system_device,
    list_microphone_devices,
    list_system_audio_devices,
)
from app.history import HistoryManager
from app.history_window import HistoryWindow
from app.settings import SettingsManager
from app.workers import MixWorker, TranscribeWorker, TranslateWorker


class DeviceListDialog(QDialog):
    """Dialog that shows parsed FFmpeg audio devices and lets the user copy or select one."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("音频设备列表")
        self.setMinimumSize(650, 450)
        self.selected_device_name = ""

        layout = QVBoxLayout(self)

        self.label = QLabel("选择一个音频设备，点击“复制设备名”或“填入设备名”：")
        layout.addWidget(self.label)

        self.list_widget = QListWidget()
        self.list_widget.setSpacing(4)
        layout.addWidget(self.list_widget)

        self.detail_label = QLabel("设备详情：")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        button_row = QHBoxLayout()
        self.copy_btn = QPushButton("复制设备名")
        self.copy_btn.clicked.connect(self._copy_name)
        self.fill_btn = QPushButton("填入设备名")
        self.fill_btn.clicked.connect(self._fill_name)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.reject)
        button_row.addWidget(self.copy_btn)
        button_row.addWidget(self.fill_btn)
        button_row.addStretch()
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

        self.list_widget.currentItemChanged.connect(self._on_selection_changed)

    def load_devices(self, raw_output: str):
        devices = parse_audio_devices(raw_output)
        audio_devices = [d for d in devices if d.kind.lower() == "audio"]

        if not audio_devices:
            item = QListWidgetItem("未找到音频设备")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.list_widget.addItem(item)
            return

        for device in audio_devices:
            item = QListWidgetItem(device.display_text())
            item.setData(Qt.UserRole, device)
            self.list_widget.addItem(item)

    def _current_device(self):
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous):
        device = current.data(Qt.UserRole) if current else None
        if device is None:
            self.detail_label.setText("设备详情：")
            self.copy_btn.setEnabled(False)
            self.fill_btn.setEnabled(False)
            return
        if isinstance(device, dict):
            name = device.get("name", "")
            kind = device.get("kind", "")
            alt = device.get("alternative_name", "") or device.get("sample_rate", "")
            self.detail_label.setText(
                f"设备详情：\n名称：{name}\n类型：{kind}\n其他：{alt}"
            )
            self.copy_btn.setEnabled(True)
            self.fill_btn.setEnabled(True)
            self.selected_device_name = name
        else:
            self.detail_label.setText(
                f"设备详情：\n名称：{device.name}\n类型：{device.kind}\n替代名：{device.alternative_name or '无'}"
            )
            self.copy_btn.setEnabled(True)
            self.fill_btn.setEnabled(True)
            self.selected_device_name = device.name

    def _copy_name(self):
        if self.selected_device_name:
            QApplication.clipboard().setText(self.selected_device_name)
            QMessageBox.information(self, "已复制", f"已复制到剪贴板：\n{self.selected_device_name}")

    def _fill_name(self):
        if self.selected_device_name:
            self.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self.copy_btn.setEnabled(False)
        self.fill_btn.setEnabled(False)


_STATE_LABELS = {
    "idle": "等待操作",
    "recording": "正在录制",
    "stopping": "正在停止",
    "recorded": "录音完成",
    "mixing": "正在混音",
    "transcribing": "正在转录",
    "translating": "正在翻译",
    "done": "完成",
    "error": "发生错误",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EchoScribe")
        self.setMinimumSize(900, 750)

        self.settings = SettingsManager()
        self.config = self.settings.load()
        self.history = HistoryManager()

        self.recorder: AudioRecorder | None = None
        self.current_mixed_path: Path | None = None
        self.current_transcription: str = ""
        self.current_translation: str = ""
        self._recording_start_time: float = 0

        self._build_ui()
        self._load_settings_to_ui()
        self._update_state("idle")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Settings
        layout.addWidget(QLabel("<h1>EchoScribe</h1>"))

        layout.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.api_key_input)

        layout.addWidget(QLabel("麦克风设备名:"))
        self.mic_device_input = QLineEdit()
        layout.addWidget(self.mic_device_input)

        layout.addWidget(QLabel("系统声音设备 (用于录制浏览器等软件):"))
        self.system_device_input = QLineEdit()
        self.system_device_input.setPlaceholderText("留空则使用默认设备")
        layout.addWidget(self.system_device_input)

        # Model selection
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("转录模型:"))
        self.whisper_model_combo = QComboBox()
        for model_id, model_name in self.settings.WHISPER_MODELS:
            self.whisper_model_combo.addItem(model_name, model_id)
        model_row.addWidget(self.whisper_model_combo)

        model_row.addWidget(QLabel("翻译模型:"))
        self.translation_model_combo = QComboBox()
        for model_id, model_name in self.settings.TRANSLATION_MODELS:
            self.translation_model_combo.addItem(model_name, model_id)
        model_row.addWidget(self.translation_model_combo)
        model_row.addStretch()
        layout.addLayout(model_row)

        settings_row = QHBoxLayout()
        self.save_settings_btn = QPushButton("保存设置")
        self.save_settings_btn.clicked.connect(self._save_settings)
        self.list_mic_devices_btn = QPushButton("列出麦克风设备")
        self.list_mic_devices_btn.clicked.connect(self._list_mic_devices)
        self.list_system_devices_btn = QPushButton("列出系统音频设备")
        self.list_system_devices_btn.clicked.connect(self._list_system_devices)
        settings_row.addWidget(self.save_settings_btn)
        settings_row.addWidget(self.list_mic_devices_btn)
        settings_row.addWidget(self.list_system_devices_btn)
        settings_row.addStretch()
        layout.addLayout(settings_row)

        # Recording controls
        controls_row = QHBoxLayout()
        self.start_btn = QPushButton("开始录制")
        self.start_btn.clicked.connect(self._start_recording)
        self.stop_btn = QPushButton("停止录制")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_recording)
        self.transcribe_btn = QPushButton("转录")
        self.transcribe_btn.setEnabled(False)
        self.transcribe_btn.clicked.connect(self._do_transcribe)
        self.translate_btn = QPushButton("翻译")
        self.translate_btn.setEnabled(False)
        self.translate_btn.clicked.connect(self._do_translate)
        controls_row.addWidget(self.start_btn)
        controls_row.addWidget(self.stop_btn)
        controls_row.addWidget(self.transcribe_btn)
        controls_row.addWidget(self.translate_btn)
        controls_row.addStretch()
        layout.addLayout(controls_row)

        # Status
        self.status_label = QLabel("当前状态：等待操作")
        self.recording_timer = QTimer(self)
        self.recording_timer.timeout.connect(self._update_recording_timer)
        layout.addWidget(self.status_label)

        # Waveform display
        self.waveform_label = QLabel("声纹:")
        layout.addWidget(self.waveform_label)
        self.waveform_area = QScrollArea()
        self.waveform_area.setWidgetResizable(True)
        self.waveform_area.setMinimumHeight(80)
        self.waveform_area.setFrameStyle(QFrame.NoFrame)
        self.waveform_canvas = QLabel()
        self.waveform_canvas.setMinimumHeight(60)
        self.waveform_area.setWidget(self.waveform_canvas)
        layout.addWidget(self.waveform_area)

        # Transcription
        layout.addWidget(QLabel("转录结果:"))
        self.transcription_edit = QTextEdit()
        self.transcription_edit.setReadOnly(True)
        layout.addWidget(self.transcription_edit)

        # Translation
        layout.addWidget(QLabel("翻译结果:"))
        self.translation_edit = QTextEdit()
        self.translation_edit.setReadOnly(True)
        layout.addWidget(self.translation_edit)

        # Export
        self.export_btn = QPushButton("导出 TXT")
        self.export_btn.clicked.connect(self._export_txt)
        layout.addWidget(self.export_btn)

        # History button
        self.history_btn = QPushButton("历史记录")
        self.history_btn.clicked.connect(self._open_history_window)
        layout.addWidget(self.history_btn)

        self._history_window: HistoryWindow | None = None

    def _load_settings_to_ui(self):
        self.api_key_input.setText(self.config.get("api_key", ""))
        self.mic_device_input.setText(self.config.get("mic_device_name", ""))
        self.system_device_input.setText(self.config.get("system_device_name", ""))

        # Set model combos
        whisper_model = self.config.get("whisper_model", "whisper-1")
        for i in range(self.whisper_model_combo.count()):
            if self.whisper_model_combo.itemData(i) == whisper_model:
                self.whisper_model_combo.setCurrentIndex(i)
                break

        translation_model = self.config.get("translation_model", "deepseek-v4-flash")
        for i in range(self.translation_model_combo.count()):
            if self.translation_model_combo.itemData(i) == translation_model:
                self.translation_model_combo.setCurrentIndex(i)
                break

    def _update_state(self, state: str, message: str | None = None):
        label = _STATE_LABELS.get(state, state)
        if message:
            self.status_label.setText(f"当前状态：{label} - {message}")
        else:
            self.status_label.setText(f"当前状态：{label}")

        self._state = state
        is_recording = state == "recording"
        is_busy = state in ("stopping", "mixing", "transcribing", "translating")

        # Check for recorded files
        has_recording = False
        if self.current_mixed_path:
            has_recording = True
        elif self.recorder:
            if hasattr(self.recorder, 'system_path') and self.recorder.system_path.exists():
                has_recording = True
            elif hasattr(self.recorder, 'mic_path') and self.recorder.mic_path.exists():
                has_recording = True

        self.start_btn.setEnabled(not is_recording and not is_busy)
        self.stop_btn.setEnabled(is_recording)

        # Enable transcribe/translate buttons only if they exist
        if hasattr(self, 'transcribe_btn'):
            self.transcribe_btn.setEnabled(bool(has_recording) and not is_busy)
        if hasattr(self, 'translate_btn'):
            self.translate_btn.setEnabled(bool(self.current_transcription) and not is_busy)

        # Start/stop recording timer and waveform
        if is_recording:
            self._recording_start_time = time.time()
            self.recording_timer.start(100)  # Update every 100ms for waveform
        else:
            self.recording_timer.stop()

    def _update_recording_timer(self):
        if self._state == "recording" and self._recording_start_time > 0:
            elapsed = int(time.time() - self._recording_start_time)
            mins = elapsed // 60
            secs = elapsed % 60
            self.status_label.setText(f"正在录制 {mins:02d}:{secs:02d}")

            # Update waveform
            self._update_waveform()

    def _update_waveform(self):
        """Draw audio waveform from recorder."""
        if not self.recorder:
            return

        # Get recent audio data from both channels
        system_audio = []
        mic_audio = []

        if hasattr(self.recorder, '_system_audio') and self.recorder._system_audio:
            with self.recorder._lock:
                system_audio = self.recorder._system_audio[-10:]  # Last 10 chunks
                system_audio = [chunk.copy() for chunk in system_audio]
        if hasattr(self.recorder, '_mic_audio') and self.recorder._mic_audio:
            with self.recorder._lock:
                mic_audio = self.recorder._mic_audio[-10:]
                mic_audio = [chunk.copy() for chunk in mic_audio]

        if not system_audio and not mic_audio:
            return

        # Combine data
        import numpy as np
        all_data = []
        for chunk in system_audio + mic_audio:
            if len(chunk) > 0:
                all_data.append(np.abs(chunk).flatten())
        if not all_data:
            return

        audio_data = np.concatenate(all_data)
        if len(audio_data) == 0:
            return

        # Downsample for display
        max_points = 500
        if len(audio_data) > max_points:
            indices = np.linspace(0, len(audio_data) - 1, max_points, dtype=int)
            audio_data = audio_data[indices]

        # Create waveform image
        width = max(800, len(audio_data) * 3)
        height = 60
        from PySide6.QtGui import QPixmap
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(30, 30, 30))

        painter = QPainter(pixmap)
        pen = QPen(QColor(0, 200, 100))
        pen.setWidth(1)
        painter.setPen(pen)

        # Draw waveform
        mid = height // 2
        for i, amp in enumerate(audio_data):
            x = i * 3
            h = int(amp * mid * 0.9)
            painter.drawLine(x, mid - h, x, mid + h)

        painter.end()
        self.waveform_canvas.setPixmap(pixmap)

    def _save_settings(self):
        self.config["api_key"] = self.api_key_input.text().strip()
        self.config["mic_device_name"] = self.mic_device_input.text().strip()
        self.config["system_device_name"] = self.system_device_input.text().strip()
        self.config["whisper_model"] = self.whisper_model_combo.currentData()
        self.config["translation_model"] = self.translation_model_combo.currentData()
        self.settings.save(self.config)
        QMessageBox.information(self, "设置", "设置已保存到 config.json")

    def _list_mic_devices(self):
        devices = list_microphone_devices()
        dialog = DeviceListDialog(self)
        dialog.setWindowTitle("麦克风设备列表")
        for d in devices:
            item = QListWidgetItem(f"{d['name']} (index={d['index']}, {d['sample_rate']}Hz)")
            item.setData(Qt.UserRole, d)
            dialog.list_widget.addItem(item)
        if dialog.exec() == QDialog.Accepted and dialog.selected_device_name:
            self.mic_device_input.setText(str(dialog.selected_device_name))

    def _list_system_devices(self):
        # PyAudioWPatch always supports WASAPI loopback
        devices = list_system_audio_devices()
        dialog = DeviceListDialog(self)
        dialog.setWindowTitle("系统音频设备列表")
        for d in devices:
            item = QListWidgetItem(f"{d['name']} (index={d['index']}, {d['sample_rate']}Hz)")
            item.setData(Qt.UserRole, d)
            dialog.list_widget.addItem(item)
        if dialog.exec() == QDialog.Accepted and dialog.selected_device_name:
            self.system_device_input.setText(str(dialog.selected_device_name))

    def _validate_before_record(self) -> bool:
        # Now using PyAudioWPatch, no FFmpeg check needed
        return True

    def _start_recording(self):
        if not self._validate_before_record():
            return

        output_dir = self.config.get("output_dir", "recordings")

        # Get microphone device index from input (or use default)
        mic_input = self.mic_device_input.text().strip()
        if mic_input:
            try:
                mic_device_index = int(mic_input)
            except ValueError:
                # Find device by name
                devices = list_microphone_devices()
                mic_device_index = -1
                for d in devices:
                    if mic_input.lower() in d["name"].lower():
                        mic_device_index = d["index"]
                        break
                if mic_device_index == -1:
                    QMessageBox.warning(self, "错误", f"未找到麦克风设备: {mic_input}")
                    return
        else:
            mic_device_index = -1  # Use default

        self.recorder = AudioRecorder(Path(output_dir), mic_device_index)
        try:
            self.recorder.start()
        except Exception as exc:
            QMessageBox.critical(self, "录音失败", f"启动录音失败: {exc}")
            self.recorder = None
            return

        self.current_mixed_path = None
        self.current_transcription = ""
        self.current_translation = ""
        self.last_history_id = None
        self.transcription_edit.clear()
        self.translation_edit.clear()

        self._update_state("recording")

    def _stop_recording(self):
        """Stop recording and save audio files."""
        if self.recorder is None:
            return
        self._update_state("stopping")

        self.mix_worker = MixWorker(self.recorder)
        self.mix_worker.finished.connect(self._on_stop_finished)
        self.mix_worker.error.connect(self._on_mix_error)
        self.mix_worker.start()

    def _on_stop_finished(self, mixed_path: Path):
        """Recording stopped, ready for transcribe."""
        self.current_mixed_path = mixed_path
        self._update_state("recorded")
        self.status_label.setText("录音完成，请点击“转录”按钮进行转录")

    def _do_transcribe(self):
        """Manually start transcription."""
        if not self.current_mixed_path:
            QMessageBox.warning(self, "提示", "没有录音文件可转录。")
            return

        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "提示", "请先填写 aihubmix API Key。")
            return

        self._update_state("transcribing")
        self.transcribe_worker = TranscribeWorker(
            self.current_mixed_path,
            api_key,
            self.config.get("base_url", "https://aihubmix.com/v1"),
            self.whisper_model_combo.currentData(),
        )
        self.transcribe_worker.finished.connect(self._on_transcribe_finished)
        self.transcribe_worker.error.connect(self._on_transcribe_error)
        self.transcribe_worker.start()

    def _do_translate(self):
        """Manually start translation."""
        if not self.current_transcription:
            QMessageBox.warning(self, "提示", "没有转录文本可翻译。")
            return

        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "提示", "请先填写 aihubmix API Key。")
            return

        self._update_state("translating")
        self.translate_worker = TranslateWorker(
            self.current_transcription,
            api_key,
            self.config.get("base_url", "https://aihubmix.com/v1"),
            self.translation_model_combo.currentData(),
        )
        self.translate_worker.finished.connect(self._on_translate_finished)
        self.translate_worker.error.connect(self._on_translate_error)
        self.translate_worker.start()

    def _on_mix_finished(self, mixed_path: Path):
        self.current_mixed_path = mixed_path
        self._update_state("transcribing")

        api_key = self.api_key_input.text().strip()
        if not api_key:
            self._update_state("error", "请先填写 aihubmix API Key")
            QMessageBox.warning(self, "提示", "请先填写 aihubmix API Key。")
            return

        self.transcribe_worker = TranscribeWorker(
            mixed_path,
            api_key,
            self.config.get("base_url", "https://aihubmix.com/v1"),
            self.config.get("whisper_model", "whisper-1"),
        )
        self.transcribe_worker.finished.connect(self._on_transcribe_finished)
        self.transcribe_worker.error.connect(self._on_transcribe_error)
        self.transcribe_worker.start()

    def _on_mix_error(self, message: str):
        self._update_state("error", message)
        QMessageBox.critical(self, "混音失败", message)

    def _on_transcribe_finished(self, text: str):
        self.current_transcription = text
        self.transcription_edit.setPlainText(text)
        self._update_state("done")
        self.status_label.setText("转录完成，请点击“翻译”按钮进行翻译")

        # Auto-save to history
        if self.current_mixed_path and self.current_mixed_path.exists():
            entry = {
                "transcription": self.current_transcription,
                "translation": "",
                "audio_path": str(self.current_mixed_path),
            }
            self.last_history_id = self.history.add(entry)
            self._refresh_history_window()

    def _on_transcribe_error(self, message: str):
        self._update_state("error", message)
        QMessageBox.critical(self, "转录失败", message)

    def _on_translate_finished(self, text: str):
        self.current_translation = text
        self.translation_edit.setPlainText(text)
        self._update_state("done")
        self.status_label.setText("翻译完成！")

        # Update history entry with translation
        if hasattr(self, 'last_history_id') and self.last_history_id:
            self.history.update(self.last_history_id, {"translation": text})
            self._refresh_history_window()
            self.last_history_id = None

    def _on_translate_error(self, message: str):
        self._update_state("error", message)
        QMessageBox.warning(
            self,
            "翻译失败",
            f"{message}\n\n转录结果已保留。",
        )

    def _export_txt(self):
        if not self.current_transcription and not self.current_translation:
            QMessageBox.warning(self, "提示", "暂无可导出内容。")
            return

        default_name = "echoscribe_export.txt"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 TXT",
            default_name,
            "Text Files (*.txt)",
        )
        if not path:
            return

        audio_file = str(self.current_mixed_path) if self.current_mixed_path else ""
        content = (
            "EchoScribe Export\n"
            "=================\n"
            f"Created At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Audio File: {audio_file}\n"
            "Transcription:\n"
            f"{self.current_transcription}\n\n"
            "Translation:\n"
            f"{self.current_translation}\n"
        )
        try:
            Path(path).write_text(content, encoding="utf-8")
            QMessageBox.information(self, "导出成功", f"已保存到:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _open_history_window(self):
        """Open the history window."""
        if self._history_window is None or not self._history_window.isVisible():
            self._history_window = HistoryWindow(self.config, self.history, self)
        self._history_window.show()
        self._history_window.raise_()
        self._history_window.activateWindow()

    def _refresh_history_window(self):
        """Refresh history window list if it is open."""
        if self._history_window is not None and self._history_window.isVisible():
            self._history_window._load_history()

    def closeEvent(self, event):
        if self.recorder is not None and self.recorder.is_recording():
            self.recorder.stop()
        if self._history_window is not None:
            self._history_window.close()
        event.accept()
