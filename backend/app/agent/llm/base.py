"""Provider-neutral LLM interface used by the activities."""

from typing import Any, Protocol

from app.domain import AgentStepInput, ChatMessage


class LLMError(Exception):
    """An LLM failure. `retryable=False` tells Temporal not to retry (e.g. a bad API key)."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMClient(Protocol):
    name: str

    async def step(self, request: AgentStepInput) -> ChatMessage:
        """Run one model step: given the conversation so far, return the assistant message."""
        ...

    async def complete_text(self, model: str | None, prompt: str) -> str: ...

    async def complete_json(self, model: str | None, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...
