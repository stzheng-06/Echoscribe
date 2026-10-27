"""Single-record JSON library, trash management, and legacy migration."""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audio.probe import probe_audio
from app.models import (
    JobState,
    LibraryAudio,
    LibraryRecord,
    MeetingSummary,
    TranscriptSegment,
    TranscriptionResult,
    TranslationVersion,
)
from app.storage.workspace import atomic_write_json, read_json

logger = logging.getLogger(__name__)


class LibraryService:
    """Manage schema-v2 records under ``workspace/library`` and ``.trash``."""

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir.expanduser().resolve()
        self.library_dir = self.workspace_dir / "library"
        self.trash_dir = self.workspace_dir / ".trash"
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.trash_dir.mkdir(parents=True, exist_ok=True)

    def create_record(
        self,
        source_audio: Path,
        *,
        source_type: str = "import",
        title: str | None = None,
        move: bool = False,
        record_id: str | None = None,
    ) -> LibraryRecord:
        """Copy (or explicitly move) audio into a new independent record."""
        metadata = probe_audio(source_audio)
        record = self.create_empty_record(
            source_type=source_type,
            title=title or metadata.filename,
            extension=metadata.extension,
            original_path=str(Path(metadata.path)),
            record_id=record_id,
        )
        destination = self.audio_path(record)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            if move:
                shutil.move(metadata.path, destination)
            else:
                shutil.copy2(metadata.path, destination)
            return self.finalize_audio(record.record_id)
        except Exception:
            if move and destination.exists() and not Path(metadata.path).exists():
                shutil.move(destination, metadata.path)
            shutil.rmtree(self.record_dir(record.record_id), ignore_errors=True)
            raise

    def create_empty_record(
        self,
        *,
        source_type: str,
        title: str,
        extension: str,
        original_path: str | None = None,
        record_id: str | None = None,
    ) -> LibraryRecord:
        """Create a record and return the destination path for direct recording."""
        identifier = record_id or uuid.uuid4().hex
        if not identifier or any(char in identifier for char in "\\/:"):
            raise ValueError("Invalid record ID")
        record_dir = self.library_dir / identifier
        if record_dir.exists():
            raise FileExistsError(f"Record already exists: {identifier}")
        (record_dir / "audio" / "chunks").mkdir(parents=True)
        now = _utc_now()
        suffix = extension if extension.startswith(".") else f".{extension}"
        record = LibraryRecord(
            record_id=identifier,
            title=title,
            created_at=now,
            updated_at=now,
            source_type=source_type,
            audio=LibraryAudio(
                relative_path=f"audio/original{suffix.lower()}",
                original_path=original_path,
                filename=Path(original_path).name if original_path else title,
                extension=suffix.lower(),
                available=False,
            ),
        )
        self.save(record)
        return record

    def finalize_audio(self, record_id: str) -> LibraryRecord:
        record = self.load(record_id)
        path = self.audio_path(record)
        metadata = probe_audio(path)
        if not record.audio.filename:
            record.audio.filename = metadata.filename
        record.audio.extension = metadata.extension
        record.audio.size_bytes = metadata.size_bytes
        record.audio.duration_seconds = metadata.duration_seconds
        record.audio.sample_rate = metadata.sample_rate
        record.audio.channels = metadata.channels
        record.audio.available = True
        self.save(record)
        return record

    def record_dir(self, record_id: str, *, trash: bool = False) -> Path:
        return (self.trash_dir if trash else self.library_dir) / record_id

    def audio_path(self, record: LibraryRecord, *, trash: bool = False) -> Path:
        return self.record_dir(record.record_id, trash=trash) / record.audio.relative_path

    def load(self, record_id: str, *, trash: bool = False) -> LibraryRecord:
        path = self.record_dir(record_id, trash=trash) / "record.json"
        try:
            record = LibraryRecord.from_dict(read_json(path))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Could not load library record: {record_id}") from exc
        if record.record_id != record_id:
            raise ValueError(f"Record ID does not match directory: {record_id}")
        audio_path = self.audio_path(record, trash=trash)
        record.audio.available = bool(record.audio.relative_path and audio_path.is_file())
        return record

    def save(self, record: LibraryRecord, *, trash: bool = False) -> None:
        """Atomically persist and re-read a complete record."""
        record.updated_at = _utc_now()
        path = self.record_dir(record.record_id, trash=trash) / "record.json"
        atomic_write_json(path, record.to_dict())
        LibraryRecord.from_dict(read_json(path))

    def list_records(self, *, trash: bool = False) -> list[LibraryRecord]:
        root = self.trash_dir if trash else self.library_dir
        records: list[LibraryRecord] = []
        for path in root.iterdir() if root.exists() else []:
            if not path.is_dir():
                continue
            try:
                records.append(self.load(path.name, trash=trash))
            except ValueError:
                logger.exception("Ignoring corrupt library record at %s", path)
        return records

    def search(
        self,
        query: str = "",
        *,
        status: str | None = None,
        source_type: str | None = None,
        language: str | None = None,
        sort: str = "newest",
        trash: bool = False,
    ) -> list[LibraryRecord]:
        needle = query.strip().casefold()
        records = self.list_records(trash=trash)
        if status:
            records = [item for item in records if item.status == status]
        if source_type:
            records = [item for item in records if item.source_type == source_type]
        if language:
            records = [
                item for item in records
                if item.transcript and item.transcript.language == language
            ]
        if needle:
            records = [item for item in records if needle in self._search_text(item)]
        if sort == "title":
            records.sort(key=lambda item: item.title.casefold())
        else:
            records.sort(key=lambda item: item.created_at, reverse=sort != "oldest")
        return records

    @staticmethod
    def _search_text(record: LibraryRecord) -> str:
        values = [record.title, record.audio.filename]
        if record.transcript:
            values.append(record.transcript.text)
        if record.summary:
            values.append(record.summary.markdown)
        values.extend(item.text for item in record.transcript_translations.values())
        values.extend(
            item.summary.markdown
            for item in record.summary_translations.values()
            if item.summary
        )
        return "\n".join(values).casefold()

    def rename(self, record_id: str, title: str) -> LibraryRecord:
        title = title.strip()
        if not title:
            raise ValueError("A record title cannot be empty")
        record = self.load(record_id)
        record.title = title
        self.save(record)
        return record

    def move_to_trash(self, record_id: str) -> str:
        """Move a record to trash without overwriting a conflicting old copy.

        A stale application instance or an interrupted restore can leave the same
        record ID in both locations. In that case the active copy is re-keyed so
        both records remain recoverable.
        """
        source = self.record_dir(record_id)
        record = self.load(record_id)
        destination = self.record_dir(record_id, trash=True)
        if destination.exists():
            self.load(record_id, trash=True)
            new_id = uuid.uuid4().hex
            while self.record_dir(new_id).exists() or self.record_dir(new_id, trash=True).exists():
                new_id = uuid.uuid4().hex
            old_job_id = record.job.job_id if record.job else None
            record.record_id = new_id
            if record.job and record.job.job_id == record_id:
                record.job.job_id = new_id
            atomic_write_json(source / "record.json", record.to_dict())
            destination = self.record_dir(new_id, trash=True)
            try:
                source.rename(destination)
                self.load(new_id, trash=True)
            except Exception:
                if destination.exists() and not source.exists():
                    destination.rename(source)
                record.record_id = record_id
                if record.job and old_job_id is not None:
                    record.job.job_id = old_job_id
                atomic_write_json(source / "record.json", record.to_dict())
                raise
            logger.warning(
                "Trash already contained record %s; moved active copy as %s",
                record_id,
                new_id,
            )
            return new_id
        source.rename(destination)
        return record_id

    def restore(self, record_id: str) -> None:
        source = self.record_dir(record_id, trash=True)
        self.load(record_id, trash=True)
        destination = self.record_dir(record_id)
        if destination.exists():
            raise FileExistsError(f"Library record already exists: {record_id}")
        source.rename(destination)

    def permanently_delete(self, record_id: str) -> None:
        path = self.record_dir(record_id, trash=True).resolve()
        if path.parent != self.trash_dir.resolve():
            raise ValueError("Unsafe trash path")
        self.load(record_id, trash=True)
        shutil.rmtree(path)

    def empty_trash(self) -> int:
        records = self.list_records(trash=True)
        for record in records:
            self.permanently_delete(record.record_id)
        return len(records)

    def update_transcript(self, record_id: str, result: TranscriptionResult) -> None:
        record = self.load(record_id)
        record.transcript = result
        record.status = "completed"
        record.transcript_translations.clear()
        self.save(record)

    def update_summary(self, record_id: str, summary: MeetingSummary) -> None:
        record = self.load(record_id)
        record.summary = summary
        record.status = "completed"
        record.summary_translations.clear()
        self.save(record)

    def save_translation(
        self, record_id: str, kind: str, version: TranslationVersion
    ) -> None:
        record = self.load(record_id)
        target = (
            record.transcript_translations
            if kind == "transcript"
            else record.summary_translations
        )
        target[version.language] = version
        self.save(record)

    def save_job(self, state: JobState) -> None:
        record = self.load(state.job_id)
        record.job = state
        record.status = state.status
        record.chunks["completed_ids"] = list(state.completed_chunk_ids)
        record.chunks["failed_id"] = state.failed_chunk_id
        self.save(record)

    def migrate_legacy(self) -> list[str]:
        """Merge old multi-file job directories; safe to retry after interruption."""
        migrated: list[str] = []
        for legacy_dir in self._legacy_directories():
            legacy_id = legacy_dir.name
            existing = self._record_for_legacy_id(legacy_id)
            if existing:
                self._cleanup_legacy_text(legacy_dir)
                continue
            try:
                record = self._migrate_one(legacy_dir)
            except Exception:
                logger.exception("Legacy migration failed for %s", legacy_dir)
                continue
            migrated.append(record.record_id)
        return migrated

    def _legacy_directories(self) -> list[Path]:
        ignored = {"library", ".trash", "recordings"}
        if not self.workspace_dir.exists():
            return []
        return [
            path for path in self.workspace_dir.iterdir()
            if path.is_dir() and path.name not in ignored
            and ((path / "job.json").exists() or (path / "source.json").exists())
        ]

    def _record_for_legacy_id(self, legacy_id: str) -> LibraryRecord | None:
        for record in self.list_records():
            if record.migration.get("legacy_job_id") == legacy_id:
                return record
        return None

    def _migrate_one(self, legacy_dir: Path) -> LibraryRecord:
        source = _safe_json(legacy_dir / "source.json")
        job = _safe_json(legacy_dir / "job.json")
        transcript_data = _safe_json(legacy_dir / "transcript" / "transcript.json")
        summary_data = _safe_json(legacy_dir / "summary" / "summary.json")
        raw = _safe_json(legacy_dir / "transcript" / "raw_response.json")
        source_path = _first_existing_path(
            job.get("source_audio"), source.get("path"), legacy_dir / "audio" / "original.wav"
        )
        extension = (
            source_path.suffix if source_path else str(source.get("extension", ".wav"))
        )
        title = str(source.get("filename") or (source_path.name if source_path else legacy_dir.name))
        record = self.create_empty_record(
            source_type="pc_recording" if "recording" in str(source_path).lower() else "import",
            title=title,
            extension=extension,
            original_path=str(source.get("path")) if source.get("path") else None,
        )
        try:
            if source_path and source_path.is_file():
                shutil.copy2(source_path, self.audio_path(record))
                record = self.finalize_audio(record.record_id)
            else:
                record.audio.available = False
            if transcript_data:
                transcript_data["raw_response"] = raw or transcript_data.get("raw_response", {})
                record.transcript = _transcript_from_legacy(transcript_data)
            elif (legacy_dir / "transcript" / "transcript.txt").exists():
                record.transcript = TranscriptionResult(
                    text=(legacy_dir / "transcript" / "transcript.txt").read_text(encoding="utf-8")
                )
            if summary_data:
                record.summary = _summary_from_legacy(summary_data)
            elif (legacy_dir / "summary" / "summary.md").exists():
                record.summary = MeetingSummary(
                    markdown=(legacy_dir / "summary" / "summary.md").read_text(encoding="utf-8")
                )
            if job:
                record.job = JobState(**{
                    key: value for key, value in job.items()
                    if key in JobState.__dataclass_fields__
                })
                record.status = record.job.status
            elif record.transcript or record.summary:
                record.status = "completed"
            record.chunks["items"] = _legacy_chunks(legacy_dir)
            record.migration = {"legacy_job_id": legacy_dir.name, "migrated_at": _utc_now()}
            self.save(record)
            self.load(record.record_id)
        except Exception:
            shutil.rmtree(self.record_dir(record.record_id), ignore_errors=True)
            raise
        self._cleanup_legacy_text(legacy_dir)
        if (
            source_path
            and record.source_type == "pc_recording"
            and source_path.exists()
            and _is_within(source_path, self.workspace_dir)
            and not _is_within(source_path, self.record_dir(record.record_id))
        ):
            source_path.unlink()
        return record

    @staticmethod
    def _cleanup_legacy_text(legacy_dir: Path) -> None:
        for path in legacy_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".json", ".txt", ".md"}:
                path.unlink()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        value = read_json(path)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _first_existing_path(*values: Any) -> Path | None:
    for value in values:
        if value:
            path = Path(value)
            if path.is_file():
                return path
    return None


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _transcript_from_legacy(data: dict[str, Any]) -> TranscriptionResult:
    return TranscriptionResult(
        text=str(data.get("text", "")),
        language=data.get("language"),
        duration_seconds=data.get("duration_seconds"),
        segments=[
            TranscriptSegment(**item)
            for item in data.get("segments", []) if isinstance(item, dict)
        ],
        provider=str(data.get("provider", "")),
        model=str(data.get("model", "")),
        raw_response=data.get("raw_response", {}),
    )


def _summary_from_legacy(data: dict[str, Any]) -> MeetingSummary:
    return MeetingSummary(**{
        key: value for key, value in data.items()
        if key in MeetingSummary.__dataclass_fields__
    })


def _legacy_chunks(legacy_dir: Path) -> list[dict[str, Any]]:
    chunks = []
    for path in sorted((legacy_dir / "transcript" / "chunks").glob("*.json")):
        value = _safe_json(path)
        if value:
            chunks.append(value)
    return chunks
