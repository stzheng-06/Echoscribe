"""Phase 3 tests for persistent jobs and background runners."""
import json
import wave

import pytest

from app.exceptions import JobStateError
from app.services.job_service import JobService
from app.workers.task_runner import TaskRunner


def _write_wav(path, *, seconds=0.05, sample_rate=8_000):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * int(seconds * sample_rate))


def test_job_lifecycle_is_persisted(tmp_path):
    source = tmp_path / "source.wav"
    _write_wav(source)
    service = JobService(tmp_path / "workspace")

    state, job_dir = service.create_job(
        source, mode="quick", provider="fake", model="fake-model"
    )

    assert state.status == "created"
    assert (job_dir / "source.json").exists()
    assert json.loads((job_dir / "job.json").read_text(encoding="utf-8"))["status"] == "created"

    service.transition(state, "transcribing")
    service.transition(state, "completed")
    loaded = service.load_job(state.job_id)
    assert loaded.status == "completed"
    assert loaded.updated_at >= loaded.created_at


def test_job_rejects_invalid_transition_and_records_failure(tmp_path):
    source = tmp_path / "source.wav"
    _write_wav(source)
    service = JobService(tmp_path / "workspace")
    state, _ = service.create_job(
        source, mode="meeting", provider="fake", model="fake-model"
    )

    with pytest.raises(JobStateError):
        service.transition(state, "completed")

    service.transition(state, "transcribing")
    service.transition(state, "failed", error_message="temporary provider failure")
    assert service.load_job(state.job_id).error_message == "temporary provider failure"


def test_job_can_copy_source_audio(tmp_path):
    source = tmp_path / "source.wav"
    _write_wav(source)
    service = JobService(tmp_path / "workspace")

    state, job_dir = service.create_job(
        source,
        mode="quick",
        provider="fake",
        model="fake-model",
        copy_source_audio=True,
    )

    copied = job_dir / "audio" / "original.wav"
    assert copied.exists()
    assert state.source_audio == str(copied)


def test_task_runner_emits_result_and_finished():
    events = []
    runner = TaskRunner(lambda token: "done")
    runner.signals.started.connect(lambda: events.append("started"))
    runner.signals.result.connect(lambda value: events.append(value))
    runner.signals.finished.connect(lambda: events.append("finished"))

    runner.run()

    assert events == ["started", "done", "finished"]


def test_task_runner_can_be_cancelled_before_start():
    events = []
    runner = TaskRunner(lambda token: pytest.fail("cancelled task should not execute"))
    runner.signals.cancelled.connect(lambda: events.append("cancelled"))
    runner.signals.finished.connect(lambda: events.append("finished"))

    runner.cancel()
    runner.run()

    assert events == ["cancelled", "finished"]
