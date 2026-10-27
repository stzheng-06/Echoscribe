"""Phase 5 tests for local chunking, merge, and resume behavior."""
from pathlib import Path
import wave

import pytest

from app.audio import converter
from app.audio.splitter import AudioChunk, split_audio
from app.exceptions import AudioConversionError, OperationCancelled
from app.models import AudioMetadata, TranscriptSegment, TranscriptionResult
from app.services.job_service import JobService
from app.services.transcription_service import (
    TranscriptionService,
    merge_chunk_results,
    requires_local_chunking,
    select_transcription_model,
)


def test_require_ffmpeg_reports_optional_dependency(monkeypatch):
    monkeypatch.setattr(converter.shutil, "which", lambda name: None)
    with pytest.raises(AudioConversionError, match="FFmpeg is required"):
        converter.require_ffmpeg()


def test_windows_ffmpeg_process_uses_no_console_flag():
    options = converter._subprocess_window_options("nt")

    assert options["creationflags"] & 0x08000000
    assert converter._subprocess_window_options("posix") == {}


def test_split_audio_uses_fixed_overlap_and_reuses_files(tmp_path, monkeypatch):
    source = tmp_path / "meeting.mp3"
    source.write_bytes(b"audio")
    metadata = AudioMetadata(
        path=str(source),
        filename=source.name,
        extension=".mp3",
        size_bytes=5,
        duration_seconds=125,
    )
    monkeypatch.setattr("app.audio.splitter.probe_audio", lambda path: metadata)
    commands = []

    def fake_runner(command):
        commands.append(command)
        Path(command[-1]).write_bytes(b"chunk")

    chunks = split_audio(
        source,
        tmp_path / "chunks",
        chunk_minutes=1,
        overlap_seconds=2,
        ffmpeg_path=Path("ffmpeg.exe"),
        command_runner=fake_runner,
    )

    assert [(chunk.start_seconds, chunk.end_seconds) for chunk in chunks] == [
        (0, 60),
        (58, 118),
        (116, 125),
    ]
    assert len(commands) == 3
    assert commands[0][commands[0].index("-ac") + 1] == "1"
    assert commands[0][commands[0].index("-ar") + 1] == "16000"

    split_audio(
        source,
        tmp_path / "chunks",
        chunk_minutes=1,
        overlap_seconds=2,
        command_runner=lambda command: pytest.fail("existing chunks should be reused"),
    )


def test_long_pcm_wave_splits_without_ffmpeg(tmp_path, monkeypatch):
    source = tmp_path / "pc_recording.wav"
    frame_rate = 8_000
    with wave.open(str(source), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(frame_rate)
        writer.writeframes(b"\0\0" * frame_rate * 65)
    monkeypatch.setattr(converter.shutil, "which", lambda name: None)

    chunks = split_audio(
        source, tmp_path / "chunks", chunk_minutes=1, overlap_seconds=2
    )

    assert [(item.start_seconds, item.end_seconds) for item in chunks] == [
        (0, 60), (58, 65),
    ]
    with wave.open(str(chunks[0].path), "rb") as reader:
        assert reader.getnframes() == frame_rate * 60


def test_provider_duration_limit_forces_local_chunks():
    assert not requires_local_chunking(1_500, True, 1_500)
    assert requires_local_chunking(3_511.832375, True, 1_500)
    assert requires_local_chunking(30, False, 1_500)


def test_audio_over_five_minutes_forces_whisper_large_v3():
    assert select_transcription_model("chosen-model", 300) == "chosen-model"
    assert select_transcription_model("chosen-model", 300.001) == "whisper-large-v3"
    assert select_transcription_model("chosen-model", None) == "chosen-model"


def test_transcription_service_uses_long_audio_model(tmp_path, monkeypatch):
    source = tmp_path / "long.wav"
    source.write_bytes(b"audio")
    metadata = AudioMetadata(
        path=str(source),
        filename=source.name,
        extension=".wav",
        size_bytes=5,
        duration_seconds=301,
    )
    monkeypatch.setattr(
        "app.services.transcription_service.probe_audio", lambda path: metadata
    )
    calls = []

    class Provider:
        def supports_long_audio(self):
            return True

        def transcribe(self, path, *, model, diarize, language=None):
            calls.append(model)
            return TranscriptionResult(text="done", provider="fake", model=model)

    result = TranscriptionService(Provider()).transcribe(
        source,
        model="chosen-model",
        job_dir=tmp_path,
    )

    assert calls == ["whisper-large-v3"]
    assert result.model == "whisper-large-v3"


def test_merge_offsets_segments_and_removes_exact_overlap_duplicates():
    first = TranscriptionResult(
        text="alpha beta repeated words here",
        language="en",
        segments=[TranscriptSegment(start=8, end=10, speaker="A", text="Repeated")],
        provider="fake",
        model="model",
    )
    second = TranscriptionResult(
        text="repeated words here then continue",
        language="en",
        segments=[
            TranscriptSegment(start=0, end=2, speaker="A", text="Repeated"),
            TranscriptSegment(start=2, end=3, speaker="B", text="Continue"),
        ],
        provider="fake",
        model="model",
    )

    merged = merge_chunk_results(
        [
            (AudioChunk(0, Path("zero.wav"), 0, 10), first),
            (AudioChunk(1, Path("one.wav"), 8, 18), second),
        ],
        overlap_seconds=2,
    )

    assert merged.text == "alpha beta repeated words here then continue"
    assert [segment.text for segment in merged.segments] == ["Repeated", "Continue"]
    assert merged.segments[1].start == 10
    assert merged.duration_seconds == 18


def test_chunk_transcription_resumes_without_repeating_completed_work(tmp_path, monkeypatch):
    chunks = [
        AudioChunk(0, tmp_path / "chunk_000.wav", 0, 10),
        AudioChunk(1, tmp_path / "chunk_001.wav", 8, 18),
    ]
    monkeypatch.setattr("app.services.transcription_service.split_audio", lambda *a, **k: chunks)
    completed = []
    cancelled = False

    class FirstProvider:
        def supports_long_audio(self):
            return False

        def transcribe(self, path, **kwargs):
            return TranscriptionResult(
                text="intro first chunk text", provider="fake", model="model"
            )

    def first_completed(chunk_id):
        nonlocal cancelled
        completed.append(chunk_id)
        cancelled = True

    service = TranscriptionService(FirstProvider())
    with pytest.raises(OperationCancelled):
        service.transcribe_chunked(
            tmp_path / "source.wav",
            model="model",
            diarize=False,
            language=None,
            job_dir=tmp_path,
            chunk_minutes=15,
            overlap_seconds=2,
            on_chunk_completed=first_completed,
            is_cancelled=lambda: cancelled,
        )
    assert completed == [0]

    calls = []

    class ResumeProvider:
        def supports_long_audio(self):
            return False

        def transcribe(self, path, **kwargs):
            calls.append(path)
            return TranscriptionResult(
                text="first chunk text then second chunk", provider="fake", model="model"
            )

    resumed = TranscriptionService(ResumeProvider()).transcribe_chunked(
        tmp_path / "source.wav",
        model="model",
        diarize=False,
        language=None,
        job_dir=tmp_path,
        chunk_minutes=15,
        overlap_seconds=2,
        completed_chunk_ids=[0],
    )

    assert calls == [chunks[1].path]
    assert resumed.text == "intro first chunk text then second chunk"
    assert (tmp_path / "transcript" / "transcript.json").exists()


def test_job_service_discovers_interrupted_local_job(tmp_path, monkeypatch):
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    metadata = AudioMetadata(
        path=str(source.resolve()),
        filename="source.wav",
        extension=".wav",
        size_bytes=5,
        duration_seconds=10,
    )
    monkeypatch.setattr("app.services.job_service.probe_audio", lambda path: metadata)
    service = JobService(tmp_path / "workspace")
    state, job_dir = service.create_job(
        source,
        mode="meeting",
        provider="fake",
        model="model",
        strategy="local_chunks",
    )
    service.transition(state, "transcribing")
    service.mark_chunk_completed(state, 0)

    found = service.find_resumable_job(source)

    assert found is not None
    assert found[0].job_id == state.job_id
    assert found[0].completed_chunk_ids == [0]
    assert found[1] == job_dir

    service.transition(state, "cancelled")
    service.mark_chunk_completed(state, 1)
    service.mark_chunk_failed(state, 1, RuntimeError("late callback"))
    assert state.status == "cancelled"
    assert state.completed_chunk_ids == [0]
