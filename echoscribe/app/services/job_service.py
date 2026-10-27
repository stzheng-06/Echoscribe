"""Persistent transcription job lifecycle management."""
from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.audio.probe import probe_audio
from app.exceptions import JobStateError
from app.models import JobState
from app.storage.library import LibraryService
from app.storage.workspace import atomic_write_json, create_job_directory, read_json

_TRANSITIONS: dict[str, set[str]] = {
    "created": {"probing", "ready", "transcribing", "failed", "cancelled"},
    "probing": {"ready", "failed", "cancelled"},
    "ready": {"transcribing", "failed", "cancelled"},
    "transcribing": {"summarizing", "completed", "failed", "cancelled"},
    "summarizing": {"completed", "failed", "cancelled"},
    "failed": {"transcribing", "summarizing", "cancelled"},
    "cancelled": {"transcribing", "summarizing"},
    "completed": {"summarizing"},
}


class JobService:
    """Create job workspaces and atomically persist status changes."""

    def __init__(
        self, workspace_dir: Path, *, library_service: LibraryService | None = None
    ) -> None:
        self.workspace_dir = workspace_dir.expanduser().resolve()
        self.library_service = library_service

    def create_job(
        self,
        source_audio: Path,
        *,
        mode: str,
        provider: str,
        model: str,
        requested_language: str = "auto",
        strategy: str = "direct",
        copy_source_audio: bool = False,
    ) -> tuple[JobState, Path]:
        if self.library_service is not None:
            return self._create_library_job(
                source_audio,
                mode=mode,
                provider=provider,
                model=model,
                requested_language=requested_language,
                strategy=strategy,
            )
        metadata = probe_audio(source_audio)
        job_id = uuid.uuid4().hex
        job_dir = create_job_directory(self.workspace_dir, job_id)
        stored_audio = Path(metadata.path)
        if copy_source_audio:
            stored_audio = job_dir / "audio" / f"original{metadata.extension}"
            shutil.copy2(metadata.path, stored_audio)

        now = _utc_now()
        state = JobState(
            job_id=job_id,
            mode=mode,
            status="created",
            source_audio=str(stored_audio),
            provider=provider,
            model=model,
            strategy=strategy,
            created_at=now,
            updated_at=now,
            requested_language=requested_language,
        )
        atomic_write_json(job_dir / "source.json", asdict(metadata))
        self.save_job(state)
        return state, job_dir

    def _create_library_job(
        self,
        source_audio: Path,
        *,
        mode: str,
        provider: str,
        model: str,
        requested_language: str,
        strategy: str,
    ) -> tuple[JobState, Path]:
        """Attach a job to an existing library record, or import it first."""
        assert self.library_service is not None
        record = None
        resolved = source_audio.expanduser().resolve()
        for candidate in self.library_service.list_records():
            if self.library_service.audio_path(candidate).resolve() == resolved:
                record = candidate
                break
        if record is None:
            record = self.library_service.create_record(source_audio)
        now = _utc_now()
        state = JobState(
            job_id=record.record_id,
            mode=mode,
            status="created",
            source_audio=str(self.library_service.audio_path(record)),
            provider=provider,
            model=model,
            strategy=strategy,
            created_at=now,
            updated_at=now,
            requested_language=requested_language,
        )
        self.library_service.save_job(state)
        return state, self.library_service.record_dir(record.record_id)

    def load_job(self, job_id: str) -> JobState:
        if self.library_service is not None:
            record = self.library_service.load(job_id)
            if record.job is None:
                raise JobStateError(f"Could not load job state: {job_id}")
            return record.job
        path = self.workspace_dir / job_id / "job.json"
        try:
            return JobState(**read_json(path))
        except (OSError, TypeError, ValueError, KeyError) as exc:
            raise JobStateError(f"Could not load job state: {job_id}") from exc

    def save_job(self, state: JobState) -> None:
        state.updated_at = _utc_now()
        if self.library_service is not None:
            self.library_service.save_job(state)
            return
        atomic_write_json(self.workspace_dir / state.job_id / "job.json", asdict(state))

    def find_resumable_job(self, source_audio: Path) -> tuple[JobState, Path] | None:
        """Return the newest interrupted local-chunk job for the selected source."""
        if not self.workspace_dir.exists():
            return None
        target = os.path.normcase(str(source_audio.expanduser().resolve()))
        matches: list[tuple[JobState, Path]] = []
        if self.library_service is not None:
            for record in self.library_service.list_records():
                state = record.job
                if state is None:
                    continue
                audio_path = self.library_service.audio_path(record)
                if (
                    state.strategy == "local_chunks"
                    and state.status in {"transcribing", "failed", "cancelled"}
                    and os.path.normcase(str(audio_path.resolve())) == target
                ):
                    matches.append((state, self.library_service.record_dir(record.record_id)))
            return max(matches, key=lambda item: item[0].updated_at) if matches else None
        for job_dir in self.workspace_dir.iterdir():
            if not job_dir.is_dir():
                continue
            try:
                state = self.load_job(job_dir.name)
                source = read_json(job_dir / "source.json")
            except (JobStateError, OSError, ValueError):
                continue
            original = source.get("path")
            if not isinstance(original, str):
                continue
            if (
                state.strategy == "local_chunks"
                and state.status in {"transcribing", "failed", "cancelled"}
                and os.path.normcase(str(Path(original).expanduser().resolve())) == target
            ):
                matches.append((state, job_dir))
        return max(matches, key=lambda item: item[0].updated_at) if matches else None

    def transition(
        self,
        state: JobState,
        status: str,
        *,
        error_message: str | None = None,
    ) -> JobState:
        if status == state.status:
            if error_message is not None:
                state.error_message = error_message
                self.save_job(state)
            return state
        if status not in _TRANSITIONS.get(state.status, set()):
            raise JobStateError(f"Invalid job transition: {state.status} -> {status}")
        state.status = status
        state.error_message = error_message
        if status != "failed":
            state.failed_chunk_id = None
        self.save_job(state)
        return state

    def mark_chunk_completed(self, state: JobState, chunk_id: int) -> None:
        """Persist one completed chunk immediately for restart-safe resume."""
        if state.status == "cancelled":
            return
        if state.status != "transcribing":
            raise JobStateError("Chunks can only complete while a job is transcribing")
        if chunk_id not in state.completed_chunk_ids:
            state.completed_chunk_ids.append(chunk_id)
            state.completed_chunk_ids.sort()
        state.failed_chunk_id = None
        state.error_message = None
        self.save_job(state)

    def mark_chunk_failed(self, state: JobState, chunk_id: int, error: Exception) -> None:
        """Record the exact failed chunk while preserving completed chunk IDs."""
        if state.status == "cancelled":
            return
        if state.status != "transcribing":
            raise JobStateError("Chunks can only fail while a job is transcribing")
        state.status = "failed"
        state.failed_chunk_id = chunk_id
        state.error_message = str(error)
        self.save_job(state)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
