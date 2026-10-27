"""Phase 2 tests for audio probing and cloud transcription."""
import json
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.audio.probe import probe_audio, recommended_mode
from app.exceptions import AudioValidationError, ProviderResponseError
from app.providers.openai_compatible_asr import (
    OpenAICompatibleASRProvider,
    normalize_response,
)
from app.services.transcription_service import TranscriptionService


def _write_wav(path: Path, *, seconds: float = 0.1, sample_rate: int = 8_000) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * int(seconds * sample_rate))


def test_probe_wav_metadata_and_mode(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path)

    metadata = probe_audio(path)

    assert metadata.filename == "sample.wav"
    assert metadata.duration_seconds == pytest.approx(0.1)
    assert metadata.sample_rate == 8_000
    assert metadata.channels == 1
    assert recommended_mode(metadata) == "quick"


@pytest.mark.parametrize("name", ["missing.wav", "sample.exe"])
def test_probe_rejects_invalid_files(tmp_path, name):
    path = tmp_path / name
    if name.endswith(".exe"):
        path.write_bytes(b"content")

    with pytest.raises(AudioValidationError):
        probe_audio(path)


def test_normalize_diarized_response():
    response = {
        "text": "Hello world",
        "language": "en",
        "duration": 2.5,
        "segments": [
            {"start": 0, "end": 1.2, "speaker": "A", "text": "Hello"},
            {"start": 1.2, "end": 2.5, "speaker": "B", "text": "world"},
        ],
    }

    result = normalize_response(response, provider="test", model="asr-model")

    assert result.text == "Hello world"
    assert result.language == "en"
    assert result.duration_seconds == 2.5
    assert [segment.speaker for segment in result.segments] == ["A", "B"]
    assert result.raw_response == response


def test_normalize_text_response_and_reject_missing_text():
    result = normalize_response("plain transcript", provider="test", model="asr-model")
    assert result.text == "plain transcript"
    assert result.raw_response == {"text": "plain transcript"}

    with pytest.raises(ProviderResponseError):
        normalize_response({"segments": []}, provider="test", model="asr-model")


def test_provider_builds_direct_upload_request(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path)
    calls = []

    class FakeTranscriptions:
        def create(self, **kwargs):
            calls.append(kwargs)
            assert kwargs["file"].read(4) == b"RIFF"
            return SimpleNamespace(
                text="hello",
                language="en",
                duration=0.1,
                segments=[],
                model_dump=lambda mode: {"text": "hello", "language": "en", "duration": 0.1},
            )

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=FakeTranscriptions()))
    provider = OpenAICompatibleASRProvider(
        api_key="test-key", base_url="https://example.test/v1", client=client
    )

    result = provider.transcribe(path, model="asr-model", diarize=True, language="en")

    assert result.text == "hello"
    assert calls[0]["model"] == "asr-model"
    assert calls[0]["chunking_strategy"] == "auto"
    assert calls[0]["response_format"] == "diarized_json"
    assert calls[0]["language"] == "en"


def test_whisper_large_v3_uses_plain_transcription_request(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path)
    calls = []

    class FakeTranscriptions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return "whisper transcript"

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=FakeTranscriptions()))
    provider = OpenAICompatibleASRProvider(
        api_key="test-key", base_url="https://aihubmix.com/v1", client=client
    )
    result = provider.transcribe(
        path, model="whisper-large-v3", diarize=True, language=None
    )

    assert result.text == "whisper transcript"
    assert calls[0]["model"] == "whisper-large-v3"
    assert "chunking_strategy" not in calls[0]
    assert "response_format" not in calls[0]
    assert not provider.supports_model_diarization("whisper-large-v3")


def test_service_saves_all_transcript_outputs(tmp_path):
    audio_path = tmp_path / "sample.wav"
    _write_wav(audio_path)
    normalized = normalize_response(
        {"text": "saved text", "segments": [{"text": "saved text", "start": 0}]},
        provider="fake",
        model="fake-model",
    )

    class FakeProvider:
        def transcribe(self, audio_path, *, model, diarize, language=None):
            return normalized

    job_dir = tmp_path / "job"
    result = TranscriptionService(FakeProvider()).transcribe_direct(
        audio_path, model="fake-model", job_dir=job_dir
    )

    assert result is normalized
    assert (job_dir / "transcript" / "transcript.txt").read_text(encoding="utf-8") == "saved text"
    saved = json.loads((job_dir / "transcript" / "transcript.json").read_text(encoding="utf-8"))
    assert saved["segments"][0]["text"] == "saved text"
    raw = json.loads((job_dir / "transcript" / "raw_response.json").read_text(encoding="utf-8"))
    assert raw["text"] == "saved text"
