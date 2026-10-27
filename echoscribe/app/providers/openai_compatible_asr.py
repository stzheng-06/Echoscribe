"""OpenAI-compatible cloud ASR provider."""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import openai

from app.exceptions import (
    ProviderAuthenticationError,
    ProviderAudioDurationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.models import TranscriptSegment, TranscriptionResult
from app.providers.asr_base import ASRProvider

OPENAI_COMPATIBLE_MAX_DURATION_SECONDS = 1500.0
OPENAI_COMPATIBLE_ASR_MODELS = (
    "gpt-4o-transcribe-diarize",
    "whisper-large-v3",
)


class OpenAICompatibleASRProvider(ASRProvider):
    """Transcribe with an OpenAI-compatible Audio Transcriptions endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        enable_auto_chunking: bool = True,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderAuthenticationError("An API key is required for cloud transcription")
        self._client = client or openai.OpenAI(api_key=api_key, base_url=base_url)
        self._auto_chunking = enable_auto_chunking

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str,
        diarize: bool,
        language: str | None = None,
    ) -> TranscriptionResult:
        request: dict[str, Any] = {"model": model}
        if self._auto_chunking and model != "whisper-large-v3":
            request["chunking_strategy"] = "auto"
        if language:
            request["language"] = language
        if diarize and self.supports_model_diarization(model):
            request["response_format"] = "diarized_json"

        try:
            with audio_path.open("rb") as audio_file:
                response = self._client.audio.transcriptions.create(file=audio_file, **request)
        except openai.AuthenticationError as exc:
            raise ProviderAuthenticationError("The provider rejected the API credentials") from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimitError("The provider rate limit was reached; retry later") from exc
        except openai.APITimeoutError as exc:
            raise ProviderTimeoutError("The transcription request timed out") from exc
        except openai.APIStatusError as exc:
            detail = str(exc).casefold()
            if exc.status_code == 400 and "audio duration" in detail and "maximum" in detail:
                raise ProviderAudioDurationError(
                    "The selected model rejected the audio duration"
                ) from exc
            raise ProviderResponseError(f"The transcription provider request failed: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderResponseError(f"The transcription provider request failed: {exc}") from exc
        except OSError as exc:
            raise ProviderResponseError(f"Could not read audio file: {audio_path}") from exc

        return normalize_response(response, provider="openai-compatible", model=model)

    def supports_long_audio(self) -> bool:
        return self._auto_chunking

    def max_direct_duration_seconds(self) -> float | None:
        return OPENAI_COMPATIBLE_MAX_DURATION_SECONDS

    def supports_diarization(self) -> bool:
        return True

    def supports_model_diarization(self, model: str) -> bool:
        # AiHubMix's whisper-large-v3 transcription endpoint returns plain/segment
        # output and does not use OpenAI's diarized_json response format.
        return model != "whisper-large-v3"


def normalize_response(response: Any, *, provider: str, model: str) -> TranscriptionResult:
    """Convert SDK text, verbose, or diarized responses into app models."""
    raw = _serializable_response(response)
    text = response if isinstance(response, str) else _value(response, "text")
    if not isinstance(text, str):
        raise ProviderResponseError("The transcription response did not contain text")

    segments: list[TranscriptSegment] = []
    raw_segments = _value(response, "segments") or raw.get("segments", [])
    if isinstance(raw_segments, list):
        for item in raw_segments:
            segment_text = _value(item, "text")
            if not isinstance(segment_text, str):
                continue
            segments.append(
                TranscriptSegment(
                    start=_optional_float(_value(item, "start")),
                    end=_optional_float(_value(item, "end")),
                    speaker=_optional_string(_value(item, "speaker")),
                    text=segment_text,
                )
            )

    return TranscriptionResult(
        text=text,
        language=_optional_string(_value(response, "language")),
        duration_seconds=_optional_float(_value(response, "duration")),
        segments=segments,
        provider=provider,
        model=model,
        raw_response=raw,
    )


def _serializable_response(response: Any) -> dict[str, Any]:
    if isinstance(response, str):
        return {"text": response}
    if isinstance(response, Mapping):
        value = dict(response)
    elif callable(getattr(response, "model_dump", None)):
        value = response.model_dump(mode="json")
    elif hasattr(response, "__dict__"):
        value = vars(response)
    else:
        raise ProviderResponseError("The transcription response could not be serialized")
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("The transcription response could not be serialized") from exc


def _value(container: Any, name: str) -> Any:
    if isinstance(container, Mapping):
        return container.get(name)
    return getattr(container, name, None)


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_string(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None
