from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.audio_tools import mix_audio
from app.recorder import AudioRecorder
from app.transcriber import Transcriber
from app.translator import Translator


class MixWorker(QThread):
    """Stop recording and mix audio files."""

    finished = Signal(Path)
    error = Signal(str)

    def __init__(self, recorder: AudioRecorder):
        super().__init__()
        self.recorder = recorder

    def run(self):
        try:
            system_path, mic_path = self.recorder.stop()

            # Check which files exist
            has_system = system_path.exists()
            has_mic = mic_path.exists()

            if not has_system and not has_mic:
                raise RuntimeError("没有生成任何录音文件")

            if has_system and has_mic:
                # Mix both
                mix_audio(system_path, mic_path, self.recorder.mixed_path)
                self.finished.emit(self.recorder.mixed_path)
            elif has_system:
                # Use system only
                self.finished.emit(system_path)
            else:
                # Use mic only
                self.finished.emit(mic_path)
        except Exception as exc:
            self.error.emit(str(exc))


class TranscribeWorker(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, audio_path: Path, api_key: str, base_url: str, model: str):
        super().__init__()
        self.audio_path = audio_path
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def run(self):
        try:
            transcriber = Transcriber(self.api_key, self.base_url, self.model)
            text = transcriber.transcribe(self.audio_path)
            self.finished.emit(text)
        except Exception as exc:
            self.error.emit(str(exc))


class TranslateWorker(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, text: str, api_key: str, base_url: str, model: str):
        super().__init__()
        self.text = text
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def run(self):
        try:
            translator = Translator(self.api_key, self.base_url, self.model)
            translation = translator.translate_to_chinese(self.text)
            self.finished.emit(translation)
        except Exception as exc:
            self.error.emit(str(exc))