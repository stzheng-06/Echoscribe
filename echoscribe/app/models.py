"""Core and versioned library data models for EchoScribe."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AudioMetadata:
    path: str
    filename: str
    extension: str
    size_bytes: int
    duration_seconds: float | None = None
    sample_rate: int | None = None
    channels: int | None = None


@dataclass
class TranscriptSegment:
    start: float | None = None
    end: float | None = None
    speaker: str | None = None
    text: str = ""


@dataclass
class TranscriptionResult:
    text: str
    language: str | None = None
    duration_seconds: float | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class MeetingSummary:
    title: str = ""
    overview: str = ""
    key_points: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    action_items: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_meeting: str | None = None
    markdown: str = ""
    language: str = ""
    model: str = ""
    length: str = ""
    generated_at: str = ""


@dataclass
class JobState:
    job_id: str
    mode: str
    status: str
    source_audio: str
    provider: str
    model: str
    strategy: str
    created_at: str
    updated_at: str
    requested_language: str = "auto"
    completed_chunk_ids: list[int] = field(default_factory=list)
    failed_chunk_id: int | None = None
    error_message: str | None = None


@dataclass
class LibraryAudio:
    """Audio metadata stored using paths relative to the record directory."""

    relative_path: str = ""
    original_path: str | None = None
    filename: str = ""
    extension: str = ""
    size_bytes: int = 0
    duration_seconds: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    available: bool = True


@dataclass
class TranslationVersion:
    """One complete, manually generated translation."""

    language: str
    created_at: str
    model: str
    text: str = ""
    segments: list[TranscriptSegment] = field(default_factory=list)
    summary: MeetingSummary | None = None


@dataclass
class LibraryRecord:
    """Schema-v2 representation of one audio item and all its business data."""

    record_id: str
    title: str
    created_at: str
    updated_at: str
    status: str = "created"
    source_type: str = "import"
    schema_version: int = 2
    audio: LibraryAudio = field(default_factory=LibraryAudio)
    transcript: TranscriptionResult | None = None
    summary: MeetingSummary | None = None
    transcript_translations: dict[str, TranslationVersion] = field(default_factory=dict)
    summary_translations: dict[str, TranslationVersion] = field(default_factory=dict)
    job: JobState | None = None
    chunks: dict[str, Any] = field(
        default_factory=lambda: {"items": [], "completed_ids": [], "failed_id": None}
    )
    migration: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable schema-v2 dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LibraryRecord":
        """Validate and deserialize a schema-v2 dictionary."""
        if data.get("schema_version") != 2:
            raise ValueError("Unsupported library record schema")
        record_id = data.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("Library record is missing record_id")
        audio_data = data.get("audio") if isinstance(data.get("audio"), dict) else {}
        transcript = _transcription_from_dict(data.get("transcript"))
        summary = _summary_from_dict(data.get("summary"))
        job_data = data.get("job")
        job = JobState(**job_data) if isinstance(job_data, dict) else None
        return cls(
            record_id=record_id,
            title=str(data.get("title", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            status=str(data.get("status", "created")),
            source_type=str(data.get("source_type", "import")),
            audio=LibraryAudio(**{
                key: value for key, value in audio_data.items()
                if key in LibraryAudio.__dataclass_fields__
            }),
            transcript=transcript,
            summary=summary,
            transcript_translations=_translations_from_dict(
                data.get("transcript_translations")
            ),
            summary_translations=_translations_from_dict(data.get("summary_translations")),
            job=job,
            chunks=data.get("chunks") if isinstance(data.get("chunks"), dict) else {},
            migration=data.get("migration") if isinstance(data.get("migration"), dict) else {},
        )


def _transcription_from_dict(value: Any) -> TranscriptionResult | None:
    if not isinstance(value, dict):
        return None
    segments = [
        TranscriptSegment(**item)
        for item in value.get("segments", [])
        if isinstance(item, dict)
    ]
    return TranscriptionResult(
        text=str(value.get("text", "")),
        language=value.get("language"),
        duration_seconds=value.get("duration_seconds"),
        segments=segments,
        provider=str(value.get("provider", "")),
        model=str(value.get("model", "")),
        raw_response=value.get("raw_response", {})
        if isinstance(value.get("raw_response", {}), dict)
        else {"value": value.get("raw_response")},
    )


def _summary_from_dict(value: Any) -> MeetingSummary | None:
    if not isinstance(value, dict):
        return None
    return MeetingSummary(
        title=str(value.get("title", "")),
        overview=str(value.get("overview", "")),
        key_points=list(value.get("key_points", [])),
        decisions=list(value.get("decisions", [])),
        action_items=list(value.get("action_items", [])),
        open_questions=list(value.get("open_questions", [])),
        next_meeting=value.get("next_meeting"),
        markdown=str(value.get("markdown", "")),
        language=str(value.get("language", "")),
        model=str(value.get("model", "")),
        length=str(value.get("length", "")),
        generated_at=str(value.get("generated_at", "")),
    )


def _translations_from_dict(value: Any) -> dict[str, TranslationVersion]:
    if not isinstance(value, dict):
        return {}
    translations: dict[str, TranslationVersion] = {}
    for language, raw in value.items():
        if not isinstance(raw, dict):
            continue
        segments = [
            TranscriptSegment(**item)
            for item in raw.get("segments", [])
            if isinstance(item, dict)
        ]
        translations[str(language)] = TranslationVersion(
            language=str(raw.get("language", language)),
            created_at=str(raw.get("created_at", "")),
            model=str(raw.get("model", "")),
            text=str(raw.get("text", "")),
            segments=segments,
            summary=_summary_from_dict(raw.get("summary")),
        )
    return translations
