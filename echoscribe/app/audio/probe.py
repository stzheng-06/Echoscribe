"""Validate imported audio files and probe lightweight metadata."""
from __future__ import annotations

import logging
import wave
from pathlib import Path

from mutagen import File as MutagenFile

from app.exceptions import AudioValidationError
from app.models import AudioMetadata

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = frozenset({".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".flac"})


def probe_audio(path: Path) -> AudioMetadata:
    """Validate *path* and return any metadata that can be read safely."""
    path = path.expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise AudioValidationError(f"Audio file does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise AudioValidationError(f"Unsupported file type '{path.suffix}'. Supported: {supported}")

    try:
        size_bytes = path.stat().st_size
        with path.open("rb") as stream:
            stream.read(1)
    except OSError as exc:
        raise AudioValidationError(f"Audio file is not readable: {path}") from exc
    if size_bytes <= 0:
        raise AudioValidationError("Audio file is empty")

    duration, sample_rate, channels = _read_metadata(path)
    return AudioMetadata(
        path=str(path),
        filename=path.name,
        extension=path.suffix.lower(),
        size_bytes=size_bytes,
        duration_seconds=duration,
        sample_rate=sample_rate,
        channels=channels,
    )


def recommended_mode(metadata: AudioMetadata) -> str | None:
    """Return the PRD mode recommendation, or ``None`` if duration is unknown."""
    if metadata.duration_seconds is None:
        return None
    return "quick" if metadata.duration_seconds <= 600 else "meeting"


def _read_metadata(path: Path) -> tuple[float | None, int | None, int | None]:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as audio:
                rate = audio.getframerate()
                frames = audio.getnframes()
                return (frames / rate if rate else None, rate or None, audio.getnchannels() or None)
        except (OSError, EOFError, wave.Error):
            logger.info("WAV metadata unavailable for %s", path)

    try:
        audio = MutagenFile(path)
        info = getattr(audio, "info", None)
        if info is None:
            return None, None, None
        duration = _positive_float(getattr(info, "length", None))
        sample_rate = _positive_int(getattr(info, "sample_rate", None))
        channels = _positive_int(getattr(info, "channels", None))
        return duration, sample_rate, channels
    except Exception as exc:  # Metadata failure must not prevent direct upload.
        logger.info("Audio metadata unavailable for %s: %s", path, exc)
        return None, None, None


def _positive_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _positive_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
