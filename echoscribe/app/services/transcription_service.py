"""Direct-upload transcription orchestration and output persistence."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.audio.probe import probe_audio
from app.audio.splitter import AudioChunk, split_audio
from app.exceptions import OperationCancelled
from app.models import TranscriptSegment, TranscriptionResult
from app.providers.asr_base import ASRProvider
from app.storage.workspace import atomic_write_json, atomic_write_text, read_json
from app.storage.library import LibraryService


LONG_AUDIO_MODEL_THRESHOLD_SECONDS = 5 * 60
LONG_AUDIO_TRANSCRIPTION_MODEL = "whisper-large-v3"


def select_transcription_model(
    requested_model: str, duration_seconds: float | None
) -> str:
    """Force the long-audio model for sources longer than five minutes."""
    if (
        duration_seconds is not None
        and duration_seconds > LONG_AUDIO_MODEL_THRESHOLD_SECONDS
    ):
        return LONG_AUDIO_TRANSCRIPTION_MODEL
    return requested_model


class TranscriptionService:
    """Coordinate validated direct uploads through an ASR provider."""

    def __init__(
        self,
        provider: ASRProvider,
        *,
        library_service: LibraryService | None = None,
        record_id: str | None = None,
    ) -> None:
        self._provider = provider
        self._library_service = library_service
        self._record_id = record_id

    def transcribe_direct(
        self,
        audio_path: Path,
        *,
        model: str,
        diarize: bool = False,
        language: str | None = None,
        job_dir: Path | None = None,
    ) -> TranscriptionResult:
        """Validate, transcribe, and optionally persist one source file."""
        metadata = probe_audio(audio_path)
        model = select_transcription_model(model, metadata.duration_seconds)
        result = self._provider.transcribe(
            Path(metadata.path), model=model, diarize=diarize, language=language
        )
        if self._library_service and self._record_id:
            self._library_service.update_transcript(self._record_id, result)
        elif job_dir is not None:
            save_transcription_outputs(job_dir, result)
        return result

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str,
        diarize: bool = False,
        language: str | None = None,
        job_dir: Path,
        chunk_minutes: int = 10,
        overlap_seconds: float = 2,
        completed_chunk_ids: list[int] | None = None,
        on_chunk_completed: Callable[[int], None] | None = None,
        on_chunk_failed: Callable[[int, Exception], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> TranscriptionResult:
        """Use direct upload when supported, otherwise use resumable local chunks."""
        metadata = probe_audio(audio_path)
        model = select_transcription_model(model, metadata.duration_seconds)
        maximum_method = getattr(
            self._provider, "max_direct_duration_seconds", lambda: None
        )
        if not requires_local_chunking(
            metadata.duration_seconds,
            self._provider.supports_long_audio(),
            maximum_method(),
        ):
            return self.transcribe_direct(
                audio_path,
                model=model,
                diarize=diarize,
                language=language,
                job_dir=job_dir,
            )
        return self.transcribe_chunked(
            audio_path,
            model=model,
            diarize=diarize,
            language=language,
            job_dir=job_dir,
            chunk_minutes=chunk_minutes,
            overlap_seconds=overlap_seconds,
            completed_chunk_ids=completed_chunk_ids,
            on_chunk_completed=on_chunk_completed,
            on_chunk_failed=on_chunk_failed,
            is_cancelled=is_cancelled,
        )
    def transcribe_chunked(
        self,
        audio_path: Path,
        *,
        model: str,
        diarize: bool,
        language: str | None,
        job_dir: Path,
        chunk_minutes: int,
        overlap_seconds: float,
        completed_chunk_ids: list[int] | None = None,
        on_chunk_completed: Callable[[int], None] | None = None,
        on_chunk_failed: Callable[[int, Exception], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> TranscriptionResult:
        """Transcribe fixed-time chunks, immediately saving each successful result."""
        chunks = split_audio(
            audio_path,
            job_dir / "audio" / "chunks",
            chunk_minutes=chunk_minutes,
            overlap_seconds=overlap_seconds,
            is_cancelled=is_cancelled,
        )
        completed = set(completed_chunk_ids or [])
        chunk_results: list[tuple[AudioChunk, TranscriptionResult]] = []
        for chunk in chunks:
            if is_cancelled and is_cancelled():
                raise OperationCancelled("Transcription was cancelled")
            result_path = job_dir / "transcript" / "chunks" / f"chunk_{chunk.chunk_id:03d}.json"
            saved_result = self._load_library_chunk(chunk.chunk_id)
            if chunk.chunk_id in completed and saved_result is not None:
                result = saved_result
            elif chunk.chunk_id in completed and result_path.exists():
                result = _load_chunk_result(result_path)
            else:
                try:
                    result = self._provider.transcribe(
                        chunk.path,
                        model=model,
                        diarize=diarize,
                        language=language,
                    )
                    if self._library_service and self._record_id:
                        self._save_library_chunk(chunk, result)
                    else:
                        _save_chunk_result(result_path, chunk, result)
                except Exception as exc:
                    if on_chunk_failed:
                        on_chunk_failed(chunk.chunk_id, exc)
                    raise
                if on_chunk_completed:
                    on_chunk_completed(chunk.chunk_id)
            chunk_results.append((chunk, result))

        merged = merge_chunk_results(chunk_results, overlap_seconds=overlap_seconds)
        if self._library_service and self._record_id:
            self._library_service.update_transcript(self._record_id, merged)
        else:
            save_transcription_outputs(job_dir, merged)
        return merged

    def _load_library_chunk(self, chunk_id: int) -> TranscriptionResult | None:
        if not self._library_service or not self._record_id:
            return None
        record = self._library_service.load(self._record_id)
        for item in record.chunks.get("items", []):
            if item.get("chunk_id") == chunk_id and isinstance(item.get("result"), dict):
                data = item["result"]
                return TranscriptionResult(
                    text=str(data.get("text", "")),
                    language=data.get("language"),
                    duration_seconds=data.get("duration_seconds"),
                    segments=[TranscriptSegment(**segment) for segment in data.get("segments", [])],
                    provider=str(data.get("provider", "")),
                    model=str(data.get("model", "")),
                    raw_response=data.get("raw_response", {}),
                )
        return None

    def _save_library_chunk(
        self, chunk: AudioChunk, result: TranscriptionResult
    ) -> None:
        assert self._library_service is not None and self._record_id is not None
        record = self._library_service.load(self._record_id)
        items = record.chunks.setdefault("items", [])
        items[:] = [item for item in items if item.get("chunk_id") != chunk.chunk_id]
        items.append({
            "chunk_id": chunk.chunk_id,
            "start_seconds": chunk.start_seconds,
            "end_seconds": chunk.end_seconds,
            "result": asdict(result),
        })
        items.sort(key=lambda item: item["chunk_id"])
        self._library_service.save(record)


def requires_local_chunking(
    duration_seconds: float | None,
    provider_supports_long_audio: bool,
    maximum_direct_seconds: float | None = None,
) -> bool:
    """Return whether a request must be split to stay within provider limits."""
    if not provider_supports_long_audio:
        return True
    return bool(
        duration_seconds is not None
        and maximum_direct_seconds is not None
        and duration_seconds > maximum_direct_seconds
    )


def save_transcription_outputs(job_dir: Path, result: TranscriptionResult) -> None:
    """Save provider and normalized outputs under ``job_dir/transcript``."""
    transcript_dir = job_dir / "transcript"
    atomic_write_json(transcript_dir / "raw_response.json", result.raw_response)
    atomic_write_json(transcript_dir / "transcript.json", asdict(result))
    atomic_write_text(transcript_dir / "transcript.txt", result.text)


def merge_chunk_results(
    chunk_results: list[tuple[AudioChunk, TranscriptionResult]],
    *,
    overlap_seconds: float,
) -> TranscriptionResult:
    """Offset timestamps and conservatively remove exact overlap duplicates."""
    merged_segments: list[TranscriptSegment] = []
    texts: list[str] = []
    raw_chunks: list[dict[str, Any]] = []
    language: str | None = None
    model = ""
    provider = ""
    duration: float | None = None
    for chunk, result in sorted(chunk_results, key=lambda item: item[0].chunk_id):
        texts.append(result.text.strip())
        raw_chunks.append(
            {
                "chunk_id": chunk.chunk_id,
                "start_seconds": chunk.start_seconds,
                "end_seconds": chunk.end_seconds,
                "response": result.raw_response,
            }
        )
        language = language or result.language
        model = model or result.model
        provider = provider or result.provider
        duration = max(duration or 0, chunk.end_seconds)
        for segment in result.segments:
            shifted = TranscriptSegment(
                start=_offset(segment.start, chunk.start_seconds),
                end=_offset(segment.end, chunk.start_seconds),
                speaker=segment.speaker,
                text=segment.text,
            )
            if merged_segments and _is_overlap_duplicate(
                merged_segments[-1], shifted, overlap_seconds
            ):
                continue
            merged_segments.append(shifted)

    return TranscriptionResult(
        text=_merge_texts(texts),
        language=language,
        duration_seconds=duration,
        segments=merged_segments,
        provider=provider,
        model=model,
        raw_response={"strategy": "local_chunks", "chunks": raw_chunks},
    )


def _save_chunk_result(path: Path, chunk: AudioChunk, result: TranscriptionResult) -> None:
    atomic_write_json(
        path,
        {
            "chunk_id": chunk.chunk_id,
            "start_seconds": chunk.start_seconds,
            "end_seconds": chunk.end_seconds,
            "result": asdict(result),
        },
    )


def _load_chunk_result(path: Path) -> TranscriptionResult:
    data = read_json(path).get("result", {})
    segments = [TranscriptSegment(**item) for item in data.get("segments", [])]
    return TranscriptionResult(
        text=str(data.get("text", "")),
        language=data.get("language"),
        duration_seconds=data.get("duration_seconds"),
        segments=segments,
        provider=str(data.get("provider", "")),
        model=str(data.get("model", "")),
        raw_response=data.get("raw_response", {}),
    )


def _offset(value: float | None, start: float) -> float | None:
    return value + start if value is not None else None


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _is_overlap_duplicate(
    previous: TranscriptSegment,
    current: TranscriptSegment,
    overlap_seconds: float,
) -> bool:
    if not current.text.strip() or _normalized_text(previous.text) != _normalized_text(current.text):
        return False
    if previous.end is None or current.start is None:
        return False
    return current.start <= previous.end + overlap_seconds + 0.25


def _merge_texts(texts: list[str]) -> str:
    merged: list[str] = []
    for text in (value for value in texts if value):
        if not merged:
            merged.extend(text.split())
            continue
        words = text.split()
        normalized_merged = [word.casefold() for word in merged]
        normalized_words = [word.casefold() for word in words]
        duplicate_count = 0
        for count in range(min(30, len(merged), len(words)), 2, -1):
            if normalized_merged[-count:] == normalized_words[:count]:
                duplicate_count = count
                break
        merged.extend(words[duplicate_count:])
    return " ".join(merged)
