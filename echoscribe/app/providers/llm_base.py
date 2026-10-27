"""Language-model provider contract."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Interface implemented by cloud and future local summary providers."""

    @abstractmethod
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
    ) -> str:
        """Return generated text without exposing provider SDK objects."""
        raise NotImplementedError
