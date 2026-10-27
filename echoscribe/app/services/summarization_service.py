"""Meeting-summary prompting, validation, formatting, and persistence."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.exceptions import SummaryParseError
from app.models import MeetingSummary
from app.providers.llm_base import LLMProvider
from app.storage.workspace import atomic_write_json, atomic_write_text
from app.storage.library import LibraryService

SYSTEM_PROMPT = """You create factual meeting summaries from transcripts.
Use only information explicitly present in the transcript. Preserve names, numbers,
dates, and technical terms. Separate decisions from discussion. Never invent owners,
deadlines, commitments, or a next meeting. Use null when an owner, deadline, or next
meeting is unknown. Return one JSON object with exactly these fields:
title, overview, key_points, decisions, action_items, open_questions, next_meeting.
Each action_items entry must contain task, owner, deadline, and status."""

SUMMARY_LENGTH_INSTRUCTIONS = {
    "short": (
        "Be concise: use a brief overview and only the most important discussion "
        "points. Preserve every explicit decision, action item, open question, and "
        "next-meeting detail."
    ),
    "medium": (
        "Use balanced detail: provide a clear overview and the main discussion "
        "points while preserving every explicit decision, action item, open "
        "question, and next-meeting detail."
    ),
    "long": (
        "Be comprehensive: provide a detailed overview and fuller discussion "
        "context. Preserve every explicit decision, action item, open question, "
        "and next-meeting detail."
    ),
}


class SummarizationService:
    """Generate a structured summary without depending on an ASR provider."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        library_service: LibraryService | None = None,
        record_id: str | None = None,
    ) -> None:
        self._provider = provider
        self._library_service = library_service
        self._record_id = record_id

    def summarize(
        self,
        transcript: str,
        *,
        model: str,
        language: str,
        length: str = "medium",
        job_dir: Path | None = None,
    ) -> MeetingSummary:
        if not transcript.strip():
            raise SummaryParseError("A non-empty transcript is required")
        try:
            length_instruction = SUMMARY_LENGTH_INSTRUCTIONS[length]
        except KeyError as exc:
            raise SummaryParseError(f"Unsupported summary length: {length}") from exc
        user_prompt = (
            f"Write the summary in {language}. {length_instruction} "
            f"Summarize this transcript:\n\n{transcript}"
        )
        raw_text = self._provider.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=model,
        )
        try:
            summary = parse_structured_summary(
                raw_text, language=language, model=model, length=length
            )
        except SummaryParseError:
            summary = MeetingSummary(
                markdown=raw_text.strip(), language=language, model=model,
                length=length, generated_at=_utc_now(),
            )
        if self._library_service and self._record_id:
            self._library_service.update_summary(self._record_id, summary)
        elif job_dir is not None:
            save_summary_outputs(job_dir, summary)
        return summary


def parse_structured_summary(
    raw_text: str,
    *,
    language: str = "en",
    model: str = "",
    length: str = "",
    generated_at: str | None = None,
) -> MeetingSummary:
    """Validate provider JSON and return a fully rendered summary."""
    cleaned = _strip_code_fence(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise SummaryParseError("The summary response was not valid JSON") from exc
    if not isinstance(data, dict):
        raise SummaryParseError("The summary response must be a JSON object")

    summary = MeetingSummary(
        title=_string(data.get("title")),
        overview=_string(data.get("overview")),
        key_points=_string_list(data.get("key_points")),
        decisions=_string_list(data.get("decisions")),
        action_items=_action_items(data.get("action_items")),
        open_questions=_string_list(data.get("open_questions")),
        next_meeting=_nullable_string(data.get("next_meeting")),
        language=language,
        model=model,
        length=length,
        generated_at=generated_at or _utc_now(),
    )
    summary.markdown = render_summary_markdown(summary, language=language)
    return summary


def save_summary_outputs(job_dir: Path, summary: MeetingSummary) -> None:
    """Atomically save normalized JSON and display-ready Markdown."""
    summary_dir = job_dir / "summary"
    atomic_write_json(summary_dir / "summary.json", asdict(summary))
    atomic_write_text(summary_dir / "summary.md", summary.markdown)


def render_summary_markdown(
    summary: MeetingSummary, *, language: str | None = None
) -> str:
    """Render the normalized summary using the PRD section order."""
    labels = _SUMMARY_LABELS.get(language or summary.language, _SUMMARY_LABELS["en"])
    lines = [
        f"# {summary.title or labels['title']}", "",
        f"## {labels['overview']}", "", summary.overview or labels["none"],
    ]
    _append_list(lines, labels["key_points"], summary.key_points, labels["none"])
    _append_list(lines, labels["decisions"], summary.decisions, labels["none"])
    lines.extend(["", f"## {labels['action_items']}", ""])
    if summary.action_items:
        for item in summary.action_items:
            task = item["task"]
            owner = item.get("owner") or labels["unknown"]
            deadline = item.get("deadline") or labels["unknown"]
            status = item.get("status") or labels["unknown"]
            lines.append(
                f"- {task} — {labels['owner']}: {owner}; "
                f"{labels['deadline']}: {deadline}; {labels['status']}: {status}"
            )
    else:
        lines.append(f"- {labels['none']}")
    _append_list(
        lines, labels["open_questions"], summary.open_questions, labels["none"]
    )
    lines.extend([
        "", f"## {labels['next_meeting']}", "",
        summary.next_meeting or labels["unknown"],
    ])
    return "\n".join(lines).strip() + "\n"


def _append_list(
    lines: list[str], heading: str, values: list[str], empty_text: str = "None"
) -> None:
    lines.extend(["", f"## {heading}", ""])
    lines.extend(f"- {value}" for value in values)
    if not values:
        lines.append(f"- {empty_text}")


_SUMMARY_LABELS = {
    "en": {
        "title": "Meeting Summary", "overview": "Overview",
        "key_points": "Key Discussion Points", "decisions": "Decisions",
        "action_items": "Action Items", "open_questions": "Open Questions",
        "next_meeting": "Next Meeting", "owner": "Owner",
        "deadline": "Deadline", "status": "Status", "unknown": "Unknown",
        "none": "None",
    },
    "zh-CN": {
        "title": "会议纪要", "overview": "会议概览", "key_points": "讨论要点",
        "decisions": "决策", "action_items": "行动项",
        "open_questions": "待确认问题", "next_meeting": "下次会议",
        "owner": "负责人", "deadline": "截止时间", "status": "状态",
        "unknown": "未知", "none": "无",
    },
    "es": {
        "title": "Resumen de la reunión", "overview": "Resumen general",
        "key_points": "Puntos clave", "decisions": "Decisiones",
        "action_items": "Acciones", "open_questions": "Preguntas abiertas",
        "next_meeting": "Próxima reunión", "owner": "Responsable",
        "deadline": "Fecha límite", "status": "Estado",
        "unknown": "Desconocido", "none": "Ninguno",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_code_fence(value: str) -> str:
    value = value.strip()
    if value.startswith("```") and value.endswith("```"):
        first_line, _, remainder = value.partition("\n")
        if first_line.lower() in {"```", "```json"}:
            return remainder.rsplit("```", 1)[0].strip()
    return value


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _nullable_string(value: Any) -> str | None:
    text = _string(value)
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _string(item))]


def _action_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        task = _string(raw_item.get("task"))
        if not task:
            continue
        items.append(
            {
                "task": task,
                "owner": _nullable_string(raw_item.get("owner")),
                "deadline": _nullable_string(raw_item.get("deadline")),
                "status": _nullable_string(raw_item.get("status")),
            }
        )
    return items
