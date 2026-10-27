"""Tests for Windows WASAPI loopback recording."""
import wave
import struct

import pytest

from app.audio.system_capture import SystemAudioRecorder
from app.exceptions import AudioCaptureError


class FakeStream:
    def __init__(self, frames_per_buffer=4, channels=2, sample_width=2):
        self.frames_per_buffer = frames_per_buffer
        self.channels = channels
        self.sample_width = sample_width
        self.read_count = 0
        self.stopped = False
        self.closed = False

    def read(self, frame_count, *, exception_on_overflow):
        assert frame_count == self.frames_per_buffer
        assert exception_on_overflow is False
        self.read_count += 1
        return b"\x00" * frame_count * self.channels * self.sample_width

    def stop_stream(self):
        self.stopped = True

    def close(self):
        self.closed = True


class FakeAudio:
    def __init__(self, stream):
        self.stream = stream
        self.terminated = False
        self.open_args = None

    def get_default_wasapi_loopback(self):
        return {
            "index": 7,
            "name": "Fake Speakers [Loopback]",
            "maxInputChannels": 2,
            "defaultSampleRate": 48_000,
        }

    def get_sample_size(self, sample_format):
        assert sample_format == 8
        return 2

    def open(self, **kwargs):
        self.open_args = kwargs
        return self.stream

    def terminate(self):
        self.terminated = True


def test_system_capture_streams_and_finalizes_wav(tmp_path):
    stream = FakeStream()
    audio = FakeAudio(stream)
    recorder = SystemAudioRecorder(
        frames_per_buffer=4,
        audio_factory=lambda: audio,
        sample_format=8,
    )
    output = tmp_path / "recordings" / "pc.wav"

    result = recorder.record(output, is_stopped=lambda: stream.read_count >= 2)

    assert result == output.resolve()
    assert output.exists()
    assert not output.with_suffix(".wav.part").exists()
    assert stream.stopped and stream.closed and audio.terminated
    assert audio.open_args["input_device_index"] == 7
    with wave.open(str(output), "rb") as wav_file:
        assert wav_file.getnchannels() == 2
        assert wav_file.getframerate() == 48_000
        assert wav_file.getnframes() == 8


def test_system_capture_rejects_empty_recording_and_removes_partial_file(tmp_path):
    stream = FakeStream()
    audio = FakeAudio(stream)
    output = tmp_path / "empty.wav"
    recorder = SystemAudioRecorder(
        audio_factory=lambda: audio,
        sample_format=8,
    )

    with pytest.raises(AudioCaptureError, match="No system audio"):
        recorder.record(output, is_stopped=lambda: True)

    assert not output.exists()
    assert not output.with_suffix(".wav.part").exists()
    assert stream.stopped and stream.closed and audio.terminated


def test_system_capture_maps_missing_loopback_device(tmp_path):
    class MissingLoopbackAudio(FakeAudio):
        def get_default_wasapi_loopback(self):
            raise OSError("WASAPI unavailable")

    stream = FakeStream()
    audio = MissingLoopbackAudio(stream)
    recorder = SystemAudioRecorder(
        audio_factory=lambda: audio,
        sample_format=8,
    )

    with pytest.raises(AudioCaptureError, match="default Windows output"):
        recorder.record(tmp_path / "missing.wav", is_stopped=lambda: False)

    assert audio.terminated


def test_stop_request_ends_capture_after_current_buffer(tmp_path):
    stream = FakeStream()
    audio = FakeAudio(stream)
    recorder = SystemAudioRecorder(
        frames_per_buffer=4,
        audio_factory=lambda: audio,
        sample_format=8,
    )
    original_read = stream.read

    def read_and_stop(*args, **kwargs):
        data = original_read(*args, **kwargs)
        recorder.request_stop()
        return data

    stream.read = read_and_stop
    output = tmp_path / "stopped.wav"

    recorder.record(output, is_stopped=lambda: False)

    assert output.exists()
    assert stream.read_count == 1


def test_capture_reports_normalized_pcm_levels(tmp_path):
    class LevelStream(FakeStream):
        def read(self, frame_count, *, exception_on_overflow):
            self.read_count += 1
            value = 0 if self.read_count == 1 else 16_384
            return struct.pack("<h", value) * frame_count * self.channels

    stream = LevelStream()
    audio = FakeAudio(stream)
    levels = []
    recorder = SystemAudioRecorder(
        frames_per_buffer=4, audio_factory=lambda: audio, sample_format=8
    )

    recorder.record(
        tmp_path / "levels.wav",
        is_stopped=lambda: stream.read_count >= 2,
        on_level=levels.append,
    )

    assert levels[0] == 0
    assert levels[1] == pytest.approx(0.5, rel=0.01)


def test_level_callback_failure_does_not_interrupt_capture(tmp_path):
    stream = FakeStream()
    audio = FakeAudio(stream)
    recorder = SystemAudioRecorder(
        frames_per_buffer=4, audio_factory=lambda: audio, sample_format=8
    )

    result = recorder.record(
        tmp_path / "callback-error.wav",
        is_stopped=lambda: stream.read_count >= 1,
        on_level=lambda _level: (_ for _ in ()).throw(RuntimeError("UI gone")),
    )

    assert result.exists()
