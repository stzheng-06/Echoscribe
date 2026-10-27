"""Manual, structure-preserving transcript and summary translation."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from app.exceptions import OperationCancelled, SummaryParseError
from app.models import (
    MeetingSummary,
    TranscriptSegment,
    TranscriptionResult,
    TranslationVersion,
)
from app.providers.llm_base import LLMProvider
from app.services.summarization_service import parse_structured_summary

SUPPORTED_TRANSLATIONS = {"en": "English", "zh-CN": "Simplified Chinese", "es": "Spanish"}
MAX_BATCH_CHARACTERS = 12_000

TRANSCRIPT_SYSTEM_PROMPT = """Translate transcript text accurately. Preserve names,
numbers, dates, technical terms, timestamps, speakers, ordering, and item IDs. Return
only a JSON object with a segments array. Each item must contain the same integer id
and a translated text string. Do not add, merge, split, or omit items."""

SUMMARY_SYSTEM_PROMPT = """Translate the supplied meeting summary while preserving
its JSON structure. Preserve names, numbers, dates, technical terms, explicit owners,
deadlines, statuses, and null values. Return only one JSON object with exactly the
same fields."""


class TranslationService:
    """Translate only when called and return a complete in-memory version."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def translate_transcript(
        self,
        transcript: TranscriptionResult,
        *,
        target_language: str,
        model: str,
        is_cancelled: Callable[[], bool] | None = None,
        max_batch_characters: int = MAX_BATCH_CHARACTERS,
    ) -> TranslationVersion:
        language_name = _language_name(target_language)
        had_segments = bool(transcript.segments)
        source_segments = transcript.segments or _plain_text_segments(
            transcript.text, max_batch_characters
        )
        translated: list[TranscriptSegment] = []
        for batch in _segment_batches(source_segments, max_batch_characters):
            if is_cancelled and is_cancelled():
                raise OperationCancelled("Translation was cancelled")
            payload = {
                "target_language": language_name,
                "segments": [
                    {"id": index, "text": segment.text}
                    for index, segment in batch
                ],
            }
            raw = self._provider.generate(
                system_prompt=TRANSCRIPT_SYSTEM_PROMPT,
                user_prompt=json.dumps(payload, ensure_ascii=False),
                model=model,
            )
            values = _parse_segment_response(raw, [index for index, _ in batch])
            for index, source in batch:
                translated.append(
                    TranscriptSegment(
                        start=source.start,
                        end=source.end,
                        speaker=source.speaker,
                        text=values[index],
                    )
                )
        if is_cancelled and is_cancelled():
            raise OperationCancelled("Translation was cancelled")
        separator = "\n" if had_segments else ""
        text = separator.join(segment.text for segment in translated).strip()
        return TranslationVersion(
            language=target_language,
            created_at=_utc_now(),
            model=model,
            text=text,
            segments=translated,
        )

    def translate_summary(
        self,
        summary: MeetingSummary,
        *,
        target_language: str,
        model: str,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> TranslationVersion:
        if is_cancelled and is_cancelled():
            raise OperationCancelled("Translation was cancelled")
        payload = asdict(summary)
        for metadata_key in ("markdown", "language", "model", "length", "generated_at"):
            payload.pop(metadata_key, None)
        raw = self._provider.generate(
            system_prompt=SUMMARY_SYSTEM_PROMPT,
            user_prompt=(
                f"Target language: {_language_name(target_language)}\n"
                f"Summary JSON:\n{json.dumps(payload, ensure_ascii=False)}"
            ),
            model=model,
        )
        if is_cancelled and is_cancelled():
            raise OperationCancelled("Translation was cancelled")
        generated_at = _utc_now()
        translated = parse_structured_summary(
            raw,
            language=target_language,
            model=model,
            length=summary.length,
            generated_at=generated_at,
        )
        return TranslationVersion(
            language=target_language,
            created_at=generated_at,
            model=model,
            summary=translated,
        )


def _segment_batches(
    segments: list[TranscriptSegment], max_characters: int
) -> list[list[tuple[int, TranscriptSegment]]]:
    if max_characters <= 0:
        raise ValueError("max_batch_characters must be positive")
    batches: list[list[tuple[int, TranscriptSegment]]] = []
    current: list[tuple[int, TranscriptSegment]] = []
    size = 0
    for index, segment in enumerate(segments):
        item_size = len(segment.text)
        if current and size + item_size > max_characters:
            batches.append(current)
            current = []
            size = 0
        current.append((index, segment))
        size += item_size
    if current:
        batches.append(current)
    return batches


def _plain_text_segments(text: str, max_characters: int) -> list[TranscriptSegment]:
    """Create safe batches for providers that returned no timed segments."""
    segments: list[TranscriptSegment] = []
    paragraphs = text.splitlines(keepends=True) or [text]
    for paragraph in paragraphs:
        while len(paragraph) > max_characters:
            split_at = paragraph.rfind(" ", 0, max_characters + 1)
            if split_at <= 0:
                split_at = max_characters
            segments.append(TranscriptSegment(text=paragraph[:split_at]))
            paragraph = paragraph[split_at:]
        if paragraph:
            segments.append(TranscriptSegment(text=paragraph))
    return segments or [TranscriptSegment(text="")]


def _parse_segment_response(raw: str, expected_ids: list[int]) -> dict[int, str]:
    cleaned = raw.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned.partition("\n")[2].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise SummaryParseError("The translation response was not valid JSON") from exc
    values = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(values, list):
        raise SummaryParseError("The translation response is missing segments")
    translated: dict[int, str] = {}
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            raise SummaryParseError("A translated segment has an invalid ID")
        text = item.get("text")
        if not isinstance(text, str):
            raise SummaryParseError("A translated segment is missing text")
        translated[item["id"]] = text
    if sorted(translated) != sorted(expected_ids):
        raise SummaryParseError("The translation changed the segment set")
    return translated


def _language_name(language: str) -> str:
    try:
        return SUPPORTED_TRANSLATIONS[language]
    except KeyError as exc:
        raise ValueError(f"Unsupported translation language: {language}") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
