"""Schema-v2 library, migration, trash, and translation regression tests."""
import json
import shutil
import wave
from dataclasses import asdict
from pathlib import Path

import pytest

from app.models import MeetingSummary, TranscriptSegment, TranscriptionResult
from app.services.summarization_service import render_summary_markdown
from app.services.translation_service import TranslationService
from app.storage.library import LibraryService
from app.storage.workspace import atomic_write_json


def _write_wav(path: Path, seconds: float = 0.05) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * int(seconds * 8_000))


def test_record_roundtrip_uses_one_business_json_and_copies_every_import(tmp_path):
    source = tmp_path / "outside" / "meeting.wav"
    _write_wav(source)
    service = LibraryService(tmp_path / "workspace")

    first = service.create_record(source)
    second = service.create_record(source)
    service.update_transcript(
        first.record_id,
        TranscriptionResult(
            text="hello", language="en", segments=[TranscriptSegment(0, 1, "A", "hello")]
        ),
    )

    loaded = service.load(first.record_id)
    assert loaded.schema_version == 2
    assert loaded.transcript.segments[0].speaker == "A"
    assert first.record_id != second.record_id
    assert service.audio_path(first).read_bytes() == source.read_bytes()
    text_outputs = [
        path for path in service.record_dir(first.record_id).rglob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".txt", ".md"}
    ]
    assert text_outputs == [service.record_dir(first.record_id) / "record.json"]


def test_old_summary_without_generation_metadata_still_loads(tmp_path):
    source = tmp_path / "source.wav"
    _write_wav(source)
    service = LibraryService(tmp_path / "workspace")
    record = service.create_record(source)
    data = record.to_dict()
    data["summary"] = {
        "title": "Historic notes",
        "overview": "Saved as written",
        "markdown": "# Historic notes\n\nSaved as written\n",
    }
    atomic_write_json(service.record_dir(record.record_id) / "record.json", data)

    loaded = service.load(record.record_id)

    assert loaded.summary.markdown == "# Historic notes\n\nSaved as written\n"
    assert loaded.summary.language == ""
    assert loaded.summary.model == ""
    assert loaded.summary.generated_at == ""


def test_library_search_sort_rename_and_trash_lifecycle(tmp_path):
    source = tmp_path / "source.wav"
    _write_wav(source)
    service = LibraryService(tmp_path / "workspace")
    record = service.create_record(source, title="Sprint review")
    service.update_transcript(record.record_id, TranscriptionResult(text="needle", language="es"))

    assert service.search("NEEDLE")[0].record_id == record.record_id
    assert service.search(language="es", source_type="import")[0].title == "Sprint review"
    assert service.rename(record.record_id, "Renamed").title == "Renamed"
    service.move_to_trash(record.record_id)
    assert not service.list_records()
    assert service.list_records(trash=True)[0].record_id == record.record_id
    service.restore(record.record_id)
    service.move_to_trash(record.record_id)
    service.permanently_delete(record.record_id)
    assert not service.list_records(trash=True)


def test_move_to_trash_rekeys_active_record_when_old_trash_copy_conflicts(tmp_path):
    source = tmp_path / "source.wav"
    _write_wav(source)
    service = LibraryService(tmp_path / "workspace")
    record = service.create_record(source, title="Duplicate after interrupted move")
    shutil.copytree(
        service.record_dir(record.record_id),
        service.record_dir(record.record_id, trash=True),
    )

    trashed_id = service.move_to_trash(record.record_id)

    assert trashed_id != record.record_id
    assert not service.record_dir(record.record_id).exists()
    old_copy = service.load(record.record_id, trash=True)
    new_copy = service.load(trashed_id, trash=True)
    assert old_copy.title == new_copy.title
    assert service.audio_path(old_copy, trash=True).read_bytes() == source.read_bytes()
    assert service.audio_path(new_copy, trash=True).read_bytes() == source.read_bytes()


def test_corrupt_record_is_ignored_by_listing(tmp_path):
    service = LibraryService(tmp_path / "workspace")
    bad = service.library_dir / "bad"
    bad.mkdir()
    (bad / "record.json").write_text("not json", encoding="utf-8")
    assert service.list_records() == []


def test_legacy_migration_combines_outputs_is_idempotent_and_marks_missing_audio(tmp_path):
    workspace = tmp_path / "workspace"
    legacy = workspace / "legacy-job"
    atomic_write_json(legacy / "source.json", {
        "path": str(tmp_path / "gone.wav"), "filename": "gone.wav", "extension": ".wav",
        "size_bytes": 5,
    })
    atomic_write_json(legacy / "job.json", {
        "job_id": "legacy-job", "mode": "meeting", "status": "failed",
        "source_audio": str(tmp_path / "gone.wav"), "provider": "fake", "model": "model",
        "strategy": "local_chunks", "created_at": "2026-01-01", "updated_at": "2026-01-02",
        "completed_chunk_ids": [0], "failed_chunk_id": 1, "error_message": "lost",
    })
    atomic_write_json(legacy / "transcript" / "transcript.json", {
        "text": "migrated", "segments": [], "provider": "fake", "model": "model",
    })

    service = LibraryService(workspace)
    migrated = service.migrate_legacy()
    assert len(migrated) == 1
    record = service.load(migrated[0])
    assert record.transcript.text == "migrated"
    assert record.audio.available is False
    assert record.job.failed_chunk_id == 1
    assert not list(legacy.rglob("*.json"))
    assert service.migrate_legacy() == []
    assert len(service.list_records()) == 1


class _TranslatingProvider:
    def __init__(self, *, fail_on_call: int | None = None):
        self.calls = []
        self.fail_on_call = fail_on_call

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("provider failure")
        payload = json.loads(kwargs["user_prompt"])
        return json.dumps({
            "segments": [
                {"id": item["id"], "text": f"T:{item['text']}"}
                for item in payload["segments"]
            ]
        })


def test_transcript_translation_preserves_segment_metadata_and_batches():
    provider = _TranslatingProvider()
    transcript = TranscriptionResult(
        text="one two",
        segments=[
            TranscriptSegment(1, 2, "A", "one"),
            TranscriptSegment(3, 4, "B", "two"),
        ],
    )
    version = TranslationService(provider).translate_transcript(
        transcript, target_language="zh-CN", model="llm", max_batch_characters=3
    )
    assert len(provider.calls) == 2
    assert [(item.start, item.end, item.speaker) for item in version.segments] == [
        (1, 2, "A"), (3, 4, "B")
    ]
    assert version.text == "T:one\nT:two"


def test_long_unsegmented_transcript_is_batched_and_failure_has_no_partial_version():
    provider = _TranslatingProvider(fail_on_call=2)
    with pytest.raises(RuntimeError, match="provider failure"):
        TranslationService(provider).translate_transcript(
            TranscriptionResult(text="a" * 25),
            target_language="es",
            model="llm",
            max_batch_characters=10,
        )
    assert len(provider.calls) == 2


def test_summary_translation_preserves_structure():
    original = MeetingSummary(
        title="Plan", overview="Overview", key_points=["Point"], decisions=["Ship"],
        action_items=[{"task": "Test", "owner": "Ana", "deadline": None, "status": "open"}],
        open_questions=["When?"], next_meeting=None,
    )
    original.markdown = render_summary_markdown(original)
    translated_data = asdict(original)
    translated_data.pop("markdown")

    class Provider:
        def generate(self, **kwargs):
            return json.dumps(translated_data)

    version = TranslationService(Provider()).translate_summary(
        original, target_language="en", model="llm"
    )
    assert version.summary.action_items[0]["owner"] == "Ana"
    assert version.summary.next_meeting is None
    assert "## Action Items" in version.summary.markdown
    assert version.summary.language == "en"
    assert version.summary.model == "llm"
    assert version.summary.generated_at == version.created_at
