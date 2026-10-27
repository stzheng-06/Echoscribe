"""OpenAI-compatible language-model provider."""
from typing import Any

import openai

from app.exceptions import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.providers.llm_base import LLMProvider


class OpenAICompatibleLLMProvider(LLMProvider):
    """Generate structured summaries through Chat Completions."""

    def __init__(self, *, api_key: str, base_url: str, client: Any | None = None) -> None:
        if not api_key.strip():
            raise ProviderAuthenticationError("An API key is required for cloud summarization")
        self._client = client or openai.OpenAI(api_key=api_key, base_url=base_url)

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
    ) -> str:
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
        except openai.AuthenticationError as exc:
            raise ProviderAuthenticationError("The provider rejected the API credentials") from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimitError("The provider rate limit was reached; retry later") from exc
        except openai.APITimeoutError as exc:
            raise ProviderTimeoutError("The summary request timed out") from exc
        except (openai.APIConnectionError, openai.APIStatusError) as exc:
            raise ProviderResponseError(f"The summary provider request failed: {exc}") from exc

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise ProviderResponseError("The summary response did not contain a message") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseError("The summary response was empty")
        return content
