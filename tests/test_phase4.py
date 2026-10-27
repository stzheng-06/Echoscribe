"""Phase 4 tests for structured meeting summarization."""
import json
from types import SimpleNamespace

import pytest

from app.exceptions import ProviderResponseError, SummaryParseError
from app.providers.openai_compatible_llm import OpenAICompatibleLLMProvider
from app.services.summarization_service import (
    SummarizationService,
    parse_structured_summary,
)


STRUCTURED_RESPONSE = """{
  "title": "Planning Review",
  "overview": "The team reviewed the release plan.",
  "key_points": ["Testing remains on schedule."],
  "decisions": ["Release on Friday."],
  "action_items": [
    {"task": "Publish notes", "owner": "Sam", "deadline": null, "status": "open"}
  ],
  "open_questions": ["Who owns deployment?"],
  "next_meeting": null
}"""


def test_parse_structured_summary_and_render_markdown():
    summary = parse_structured_summary(f"```json\n{STRUCTURED_RESPONSE}\n```")

    assert summary.title == "Planning Review"
    assert summary.action_items[0]["owner"] == "Sam"
    assert summary.action_items[0]["deadline"] is None
    assert "## Decisions" in summary.markdown
    assert "Deadline: Unknown" in summary.markdown
    assert summary.next_meeting is None


@pytest.mark.parametrize("response", ["not json", "[]", ""])
def test_structured_parser_rejects_invalid_response(response):
    with pytest.raises(SummaryParseError):
        parse_structured_summary(response)


def test_summary_service_falls_back_to_raw_markdown(tmp_path):
    class FakeProvider:
        def generate(self, **kwargs):
            return "# Provider summary\n\nUnstructured but useful."

    summary = SummarizationService(FakeProvider()).summarize(
        "A transcript",
        model="summary-model",
        language="en",
        job_dir=tmp_path,
    )

    assert summary.title == ""
    assert summary.markdown.startswith("# Provider summary")
    assert (tmp_path / "summary" / "summary.md").read_text(encoding="utf-8") == summary.markdown
    saved = json.loads((tmp_path / "summary" / "summary.json").read_text(encoding="utf-8"))
    assert saved["markdown"] == summary.markdown


def test_summary_service_prompts_for_selected_language_and_saves_json(tmp_path):
    calls = []

    class FakeProvider:
        def generate(self, **kwargs):
            calls.append(kwargs)
            return STRUCTURED_RESPONSE

    summary = SummarizationService(FakeProvider()).summarize(
        "Meeting transcript",
        model="summary-model",
        language="zh-CN",
        length="long",
        job_dir=tmp_path,
    )

    assert summary.title == "Planning Review"
    assert calls[0]["model"] == "summary-model"
    assert "zh-CN" in calls[0]["user_prompt"]
    assert "comprehensive" in calls[0]["user_prompt"]
    saved = json.loads((tmp_path / "summary" / "summary.json").read_text(encoding="utf-8"))
    assert saved["decisions"] == ["Release on Friday."]
    assert saved["language"] == "zh-CN"
    assert saved["model"] == "summary-model"
    assert saved["length"] == "long"
    assert saved["generated_at"]


@pytest.mark.parametrize(
    ("language", "heading", "action_label", "empty_text"),
    [
        ("en", "## Overview", "Owner: Unknown", "- None"),
        ("zh-CN", "## 会议概览", "负责人: 未知", "- 无"),
        ("es", "## Resumen general", "Responsable: Desconocido", "- Ninguno"),
    ],
)
def test_summary_markdown_uses_selected_language(
    language, heading, action_label, empty_text
):
    response = json.loads(STRUCTURED_RESPONSE)
    response["key_points"] = []
    response["action_items"][0]["owner"] = None
    summary = parse_structured_summary(json.dumps(response), language=language)

    assert heading in summary.markdown
    assert action_label in summary.markdown
    assert empty_text in summary.markdown


def test_summary_service_rejects_empty_transcript():
    class FakeProvider:
        def generate(self, **kwargs):
            pytest.fail("provider should not run for an empty transcript")

    with pytest.raises(SummaryParseError):
        SummarizationService(FakeProvider()).summarize(
            "  ", model="summary-model", language="en"
        )


def test_summary_service_rejects_unknown_length():
    class FakeProvider:
        def generate(self, **kwargs):
            pytest.fail("provider should not run for an invalid length")

    with pytest.raises(SummaryParseError, match="Unsupported summary length"):
        SummarizationService(FakeProvider()).summarize(
            "Transcript", model="summary-model", language="en", length="tiny"
        )


def test_openai_compatible_llm_request_is_isolated():
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            message = SimpleNamespace(content=STRUCTURED_RESPONSE)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    provider = OpenAICompatibleLLMProvider(
        api_key="test-key", base_url="https://example.test/v1", client=client
    )
    content = provider.generate(
        system_prompt="system", user_prompt="transcript", model="summary-model"
    )

    assert content == STRUCTURED_RESPONSE
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["messages"][1] == {"role": "user", "content": "transcript"}


def test_openai_compatible_llm_rejects_empty_message():
    message = SimpleNamespace(content=None)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=message)])
            )
        )
    )
    provider = OpenAICompatibleLLMProvider(
        api_key="test-key", base_url="https://example.test/v1", client=client
    )

    with pytest.raises(ProviderResponseError):
        provider.generate(system_prompt="system", user_prompt="user", model="model")
