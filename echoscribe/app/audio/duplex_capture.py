"""Clock-aligned microphone and Windows loopback capture, without extra dependencies."""
from __future__ import annotations

import logging
import math
import os
import sys
import threading
import time
import wave
from array import array
from collections import deque
from collections.abc import Callable
from pathlib import Path

from app.audio.system_capture import _normalized_pcm_level
from app.exceptions import AudioCaptureError

logger = logging.getLogger(__name__)
RATE = 48000
BLOCK = 960
LATENCY = 0.2


def _mono_pcm(data: bytes, channels: int) -> list[float]:
    samples = array('h')
    samples.frombytes(data)
    if sys.byteorder != 'little':
        samples.byteswap()
    return [sum(samples[i:i + channels]) / channels
            for i in range(0, len(samples), channels)]


class _Timeline:
    """Bounded timestamped buffers; missing output audio becomes silence."""

    def __init__(self) -> None:
        self.blocks: deque = deque()
        self.lock = threading.Lock()

    def append(self, start: float, rate: int, samples: list[float]) -> None:
        with self.lock:
            if len(self.blocks) >= 512:
                raise AudioCaptureError('Recording cannot keep up with the audio devices')
            self.blocks.append((start, rate, samples))

    def read(self, start: float, count: int) -> list[float]:
        result = [0.0] * count
        end = start + count / RATE
        with self.lock:
            while self.blocks and (
                self.blocks[0][0] + len(self.blocks[0][2]) / self.blocks[0][1] <= start
            ):
                self.blocks.popleft()
            for timestamp, rate, samples in self.blocks:
                if timestamp >= end:
                    break
                first = max(0, math.ceil((timestamp - start) * RATE))
                last = min(count, math.ceil((timestamp + len(samples) / rate - start) * RATE))
                for index in range(first, last):
                    position = max(0.0, (start + index / RATE - timestamp) * rate)
                    left = min(int(position), len(samples) - 1)
                    right = min(left + 1, len(samples) - 1)
                    fraction = position - left
                    result[index] = samples[left] + (samples[right] - samples[left]) * fraction
        return result


def _mix(left: list[float], right: list[float]) -> bytes:
    # Headroom for simultaneous speech; both sources remain audible without clipping.
    samples = array('h', (max(-32768, min(32767, round((a + b) * 0.5)))
                          for a, b in zip(left, right)))
    if sys.byteorder != 'little':
        samples.byteswap()
    return samples.tobytes()


class DuplexAudioRecorder:
    """Capture the default microphone and speakers into one 48 kHz mono WAV."""

    def __init__(self, *, backend=None) -> None:
        self._backend = backend
        self._stop = threading.Event()

    def request_stop(self) -> None:
        """Wake the disk writer; callback streams are closed by its own thread."""
        self._stop.set()

    def record(
        self, output_path: Path, *, is_stopped: Callable[[], bool],
        on_level: Callable[[float], None] | None = None,
    ) -> Path:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + '.part')
        streams = []
        audio = None
        errors: list[Exception] = []
        received = [False, False]
        timelines = [_Timeline(), _Timeline()]
        self._stop.clear()
        try:
            if self._backend is None:
                import pyaudiowpatch as backend
            else:
                backend = self._backend
            audio = backend.PyAudio()
            output = audio.get_default_wasapi_loopback()
            microphone = audio.get_default_input_device_info()
            if microphone.get('isLoopbackDevice'):
                raise AudioCaptureError('The default microphone is a loopback device')

            def callback_for(device, timeline, source_index):
                rate = int(device['defaultSampleRate'])
                channels = min(2, int(device['maxInputChannels']))
                if rate <= 0 or channels <= 0:
                    raise AudioCaptureError('An audio device has no usable input channels')
                next_time = None

                def callback(data, frame_count, timing, status):
                    nonlocal next_time
                    try:
                        if status:
                            raise AudioCaptureError(f'Audio capture interrupted (status {status})')
                        # PortAudio clocks can differ between devices. Convert each ADC
                        # timestamp to monotonic time, then keep contiguous sample timing.
                        measured = time.monotonic() - max(
                            0.0, timing['current_time'] - timing['input_buffer_adc_time']
                        )
                        if next_time is None or abs(measured - next_time) > 0.1:
                            next_time = measured
                        timeline.append(next_time, rate, _mono_pcm(data, channels))
                        received[source_index] = bool(data) or received[source_index]
                        next_time += frame_count / rate
                        return None, backend.paContinue
                    except Exception as exc:
                        errors.append(exc)
                        self._stop.set()
                        return None, backend.paAbort
                return rate, channels, callback

            for source_index, (device, timeline) in enumerate(zip((output, microphone), timelines)):
                rate, channels, callback = callback_for(device, timeline, source_index)
                streams.append(audio.open(
                    format=backend.paInt16, channels=channels, rate=rate,
                    input=True, input_device_index=int(device['index']),
                    frames_per_buffer=max(1, rate // 50), stream_callback=callback,
                    start=False,
                ))
            start = time.monotonic()
            for stream in streams:
                stream.start_stream()
            frames = 0
            with wave.open(str(temporary), 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(RATE)
                while True:
                    stopping = self._stop.is_set() or is_stopped()
                    if errors:
                        raise AudioCaptureError(str(errors[0])) from errors[0]
                    now = time.monotonic()
                    available = max(0, int((now - start - (0 if stopping else LATENCY)) * RATE))
                    while frames < available:
                        count = min(BLOCK, available - frames)
                        timestamp = start + frames / RATE
                        data = _mix(*(timeline.read(timestamp, count) for timeline in timelines))
                        wav.writeframesraw(data)
                        frames += count
                        if on_level:
                            try:
                                on_level(_normalized_pcm_level(data, 2))
                            except Exception:
                                logger.debug('Audio-level callback failed', exc_info=True)
                    if stopping:
                        break
                    if any(not stream.is_active() for stream in streams):
                        raise AudioCaptureError('Microphone or system audio device stopped')
                    self._stop.wait(0.02)
            if not frames:
                raise AudioCaptureError('No audio was captured')
            if not received[1]:
                raise AudioCaptureError('No microphone samples were received. Check microphone permissions.')
            os.replace(temporary, output_path)
            return output_path
        except (ImportError, OSError, ValueError, KeyError, RuntimeError) as exc:
            raise AudioCaptureError(
                'Could not record microphone and system audio. Check the default '
                'microphone, Windows microphone permissions, and output device. '
                f'{exc}'
            ) from exc
        finally:
            for stream in streams:
                try:
                    stream.close()
                except (OSError, RuntimeError):
                    logger.warning('Could not close audio stream', exc_info=True)
            if audio is not None:
                try:
                    audio.terminate()
                except (OSError, RuntimeError):
                    logger.warning('Could not terminate audio backend', exc_info=True)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning('Could not remove incomplete recording %s', temporary, exc_info=True)
