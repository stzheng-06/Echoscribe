"""Bidirectional capture: sample alignment, clipping and device lifecycle."""
import struct
import wave
from types import SimpleNamespace

import pytest

from app.audio.duplex_capture import DuplexAudioRecorder, _Timeline, _mix
from app.exceptions import AudioCaptureError


def test_native_rates_align_and_silence_does_not_block_microphone():
    speaker, mic = _Timeline(), _Timeline()
    speaker.append(1.0, 48000, [8000] * 480)
    mic.append(1.0, 16000, [12000] * 160)
    mixed = _mix(speaker.read(1.0, 480), mic.read(1.0, 480))
    assert struct.unpack('<480h', mixed) == (10000,) * 480
    mic.append(1.01, 16000, [12000] * 160)
    mixed = _mix(speaker.read(1.01, 480), mic.read(1.01, 480))
    assert struct.unpack('<480h', mixed) == (6000,) * 480


def test_mix_has_headroom_and_keeps_both_sources():
    assert struct.unpack('<3h', _mix([32767, -32768, 2000], [32767, -32768, 6000])) == (
        32767, -32768, 4000,
    )


@pytest.mark.parametrize('mode', [
    'normal', 'permission_denied', 'overflow', 'no_microphone_samples',
    'request_stop', 'disconnected',
])
def test_duplex_device_lifecycle(tmp_path, monkeypatch, mode):
    clock = [10.0]
    monkeypatch.setattr('app.audio.duplex_capture.time.monotonic', lambda: clock[0])
    streams = []

    class Stream:
        closed = False

        def __init__(self, kwargs):
            self.kwargs = kwargs

        def start_stream(self):
            if mode == 'no_microphone_samples' and self.kwargs['input_device_index'] == 2:
                return
            value = 8000 if self.kwargs['input_device_index'] == 1 else 12000
            self.kwargs['stream_callback'](
                struct.pack('<h', value) * 960, 960,
                {'current_time': 10.0, 'input_buffer_adc_time': 10.0},
                2 if mode == 'overflow' else 0,
            )

        def is_active(self):
            return mode != 'disconnected'

        def close(self):
            self.closed = True

    class Audio:
        terminated = False

        def get_default_wasapi_loopback(self):
            return dict(index=1, maxInputChannels=1, defaultSampleRate=48000)

        def get_default_input_device_info(self):
            return dict(index=2, maxInputChannels=1, defaultSampleRate=48000)

        def open(self, **kwargs):
            if mode == 'permission_denied' and kwargs['input_device_index'] == 2:
                raise OSError('Microphone permission denied')
            stream = Stream(kwargs)
            streams.append(stream)
            return stream

        def terminate(self):
            self.terminated = True

    audio = Audio()
    backend = SimpleNamespace(PyAudio=lambda: audio, paInt16=8, paContinue=0, paAbort=2)
    recorder = DuplexAudioRecorder(backend=backend)
    destination = tmp_path / 'meeting.wav'

    def stop():
        clock[0] = 10.02
        if mode == 'request_stop':
            recorder.request_stop()
            return False
        if mode == 'disconnected':
            return False
        return True

    expected_errors = {
        'permission_denied': 'Microphone permission denied',
        'overflow': 'Audio capture interrupted',
        'no_microphone_samples': 'No microphone samples',
        'disconnected': 'device stopped',
    }
    if mode in expected_errors:
        with pytest.raises(AudioCaptureError, match=expected_errors[mode]):
            recorder.record(destination, is_stopped=stop)
        assert not destination.exists()
    else:
        recorder.record(destination, is_stopped=stop)
        with wave.open(str(destination), 'rb') as wav:
            assert wav.getnchannels() == 1
            assert wav.getframerate() == 48000
            samples = wav.readframes(wav.getnframes())
            assert set(struct.unpack('<' + 'h' * (len(samples) // 2), samples)) == {10000}
    assert all(stream.closed for stream in streams)
    assert audio.terminated
    assert not destination.with_suffix('.wav.part').exists()


@pytest.mark.parametrize('offset', [0.0, 3600.0, 10800.0])
def test_fractional_rate_alignment_at_long_recording_offsets(offset):
    timeline = _Timeline()
    start = 100000.0 + offset
    for index in range(20):
        timeline.append(start + index * 0.02, 44100, [12000] * 882)
    for index in range(19):
        samples = timeline.read(start + index * 0.02, 960)
        # Floating point boundary rounding can affect one sample per block.
        assert sum(value == 12000 for value in samples) >= 959
    timeline.read(start + 1, 960)
    assert not timeline.blocks


def test_timestamp_gap_is_silence_instead_of_shifting_later_audio():
    timeline = _Timeline()
    timeline.append(10.0, 48000, [1000] * 960)
    timeline.append(10.04, 48000, [2000] * 960)
    assert timeline.read(10.02, 960) == [0.0] * 960
    assert timeline.read(10.04, 960) == [2000.0] * 960


def test_timeline_overload_is_explicit_and_memory_bounded():
    timeline = _Timeline()
    for index in range(512):
        timeline.append(index * 0.02, 48000, [1])
    with pytest.raises(AudioCaptureError, match='cannot keep up'):
        timeline.append(11, 48000, [1])
