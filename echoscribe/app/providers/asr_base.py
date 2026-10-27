"""Speech-to-text provider contract."""
from abc import ABC, abstractmethod
from pathlib import Path

from app.models import TranscriptionResult


class ASRProvider(ABC):
    """Interface implemented by cloud and future local ASR providers."""

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str,
        diarize: bool,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe one audio file into the normalized application model."""
        raise NotImplementedError

    @abstractmethod
    def supports_long_audio(self) -> bool:
        raise NotImplementedError

    def max_direct_duration_seconds(self) -> float | None:
        """Return a known request limit, or ``None`` when the provider has none."""
        return None

    @abstractmethod
    def supports_diarization(self) -> bool:
        raise NotImplementedError

    def supports_model_diarization(self, model: str) -> bool:
        """Return whether one selected model accepts speaker-separation requests."""
        del model
        return self.supports_diarization()
