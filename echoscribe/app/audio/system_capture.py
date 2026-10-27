"""Windows system-output recording through WASAPI loopback."""
from __future__ import annotations

import logging
import math
import os
import sys
import threading
import wave
from array import array
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.exceptions import AudioCaptureError

logger = logging.getLogger(__name__)


class SystemAudioRecorder:
    """Stream the default Windows output device directly into a PCM WAV file."""

    def __init__(
        self,
        *,
        frames_per_buffer: int = 1024,
        audio_factory: Callable[[], Any] | None = None,
        sample_format: int | None = None,
    ) -> None:
        self.frames_per_buffer = frames_per_buffer
        self._audio_factory = audio_factory
        self._sample_format = sample_format
        self._stop_requested = threading.Event()
        self._stream: Any | None = None
        self._stream_lock = threading.Lock()

    def request_stop(self) -> None:
        """Stop an active PortAudio stream so a blocking read returns promptly."""
        self._stop_requested.set()
        with self._stream_lock:
            stream = self._stream
        if stream is not None:
            try:
                stream.stop_stream()
            except (OSError, RuntimeError):
                logger.debug("Capture stream stop request was already satisfied", exc_info=True)

    def record(
        self,
        output_path: Path,
        *,
        is_stopped: Callable[[], bool],
        on_level: Callable[[float], None] | None = None,
    ) -> Path:
        """Record until ``is_stopped`` is true, then atomically finalize the WAV."""
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(output_path.suffix + ".part")
        audio = None
        stream = None
        frames_written = 0
        self._stop_requested.clear()
        try:
            if self._audio_factory is not None:
                audio = self._audio_factory()
                if self._sample_format is None:
                    raise AudioCaptureError("A sample format is required for a custom audio backend")
                sample_format = self._sample_format
            else:
                backend, default_format = _load_backend()
                audio = backend.PyAudio()
                sample_format = self._sample_format or default_format
            device = audio.get_default_wasapi_loopback()
            channels = int(device.get("maxInputChannels", 0))
            sample_rate = int(device.get("defaultSampleRate", 0))
            device_index = int(device["index"])
            if channels <= 0 or sample_rate <= 0:
                raise AudioCaptureError("The default WASAPI loopback device is invalid")
            sample_width = int(audio.get_sample_size(sample_format))
            logger.info(
                "Starting system audio capture device=%s rate=%s channels=%s",
                device.get("name", device_index),
                sample_rate,
                channels,
            )
            stream = audio.open(
                format=sample_format,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.frames_per_buffer,
            )
            with self._stream_lock:
                self._stream = stream
            with wave.open(str(temp_path), "wb") as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(sample_width)
                wav_file.setframerate(sample_rate)
                while not self._stop_requested.is_set() and not is_stopped():
                    try:
                        data = stream.read(
                            self.frames_per_buffer,
                            exception_on_overflow=False,
                        )
                    except OSError:
                        if self._stop_requested.is_set() or is_stopped():
                            break
                        raise
                    if data:
                        wav_file.writeframesraw(data)
                        frames_written += len(data) // (sample_width * channels)
                        if on_level is not None:
                            try:
                                on_level(_normalized_pcm_level(data, sample_width))
                            except Exception:
                                logger.debug(
                                    "Audio-level callback failed", exc_info=True
                                )
            if frames_written == 0:
                raise AudioCaptureError("No system audio was captured")
            os.replace(temp_path, output_path)
            logger.info("System audio capture saved to %s", output_path)
            return output_path
        except AudioCaptureError:
            raise
        except (KeyError, LookupError, OSError, RuntimeError, ValueError) as exc:
            raise AudioCaptureError(
                "Could not capture the default Windows output. Check the active output "
                "device and WASAPI availability."
            ) from exc
        finally:
            with self._stream_lock:
                self._stream = None
            if stream is not None:
                try:
                    stream.stop_stream()
                except (OSError, RuntimeError):
                    logger.debug("Capture stream was already stopped", exc_info=True)
                try:
                    stream.close()
                except (OSError, RuntimeError):
                    logger.debug("Could not close capture stream cleanly", exc_info=True)
            if audio is not None:
                try:
                    audio.terminate()
                except (OSError, RuntimeError):
                    logger.debug("Could not terminate audio backend cleanly", exc_info=True)
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    logger.warning("Could not remove incomplete capture %s", temp_path)


def _load_backend() -> tuple[Any, int]:
    try:
        import pyaudiowpatch as pyaudio
    except ImportError as exc:
        raise AudioCaptureError(
            "PC audio capture requires PyAudioWPatch. Install requirements.txt."
        ) from exc
    return pyaudio, pyaudio.paInt16


def _normalized_pcm_level(data: bytes, sample_width: int) -> float:
    """Return the RMS amplitude of little-endian PCM data in the range 0..1."""
    if not data or sample_width not in {1, 2, 3, 4}:
        return 0.0
    if sample_width == 1:
        samples = (value - 128 for value in data)
        peak = 127
        count = len(data)
    elif sample_width in {2, 4}:
        typecode = "h" if sample_width == 2 else "i"
        values = array(typecode)
        usable = len(data) - (len(data) % sample_width)
        values.frombytes(data[:usable])
        if sys.byteorder != "little":
            values.byteswap()
        samples = iter(values)
        peak = (1 << (sample_width * 8 - 1)) - 1
        count = len(values)
    else:
        usable = len(data) - (len(data) % 3)
        samples = (
            int.from_bytes(data[index:index + 3], "little", signed=True)
            for index in range(0, usable, 3)
        )
        peak = (1 << 23) - 1
        count = usable // 3
    if count == 0:
        return 0.0
    square_sum = sum(sample * sample for sample in samples)
    return min(1.0, math.sqrt(square_sum / count) / peak)
