"""Gemini adapter tests with a fake SDK client (no network, no quota)."""

from typing import Any

import pytest
from google.genai import errors as genai_errors
from google.genai import types

from app.agent.llm.base import LLMError
from app.agent.llm.gemini import GeminiClient
from app.domain import AgentStepInput, ChatMessage, ToolCall, ToolSpec

pytestmark = pytest.mark.unit

DAILY_QUOTA = {
    "error": {
        "code": 429,
        "message": "quota",
        "status": "RESOURCE_EXHAUSTED",
        "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}],
    }
}
BUSY = {"error": {"code": 503, "message": "busy", "status": "UNAVAILABLE"}}
BAD_KEY = {"error": {"code": 400, "message": "API key not valid", "status": "INVALID_ARGUMENT"}}


class FakeModels:
    def __init__(self, outcomes: dict[str, Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, Any]] = []

    async def generate_content(self, *, model: str, contents: Any, config: Any) -> types.GenerateContentResponse:
        self.calls.append((model, contents))
        outcome = self.outcomes[model]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client_with(outcomes: dict[str, Any]) -> tuple[GeminiClient, FakeModels]:
    client = GeminiClient(api_key="test", default_model="primary", fallback_models=["backup"])
    fake = FakeModels(outcomes)
    client._client = type("C", (), {"aio": type("A", (), {"models": fake})()})()  # type: ignore[assignment]
    return client, fake


def tool_call_response() -> types.GenerateContentResponse:
    part = types.Part(function_call=types.FunctionCall(name="schedule_next_wake", args={"minutes": 5, "reason": "x"}))
    content = types.Content(role="model", parts=[types.Part(text="Sleeping."), part])
    return types.GenerateContentResponse(candidates=[types.Candidate(content=content)])


def request(messages: list[ChatMessage]) -> AgentStepInput:
    spec = ToolSpec(name="schedule_next_wake", description="d", parameters={"type": "object", "properties": {}})
    return AgentStepInput(model=None, system_prompt="sys", messages=messages, tools=[spec])


async def test_step_parses_text_and_tool_calls() -> None:
    client, _ = client_with({"primary": tool_call_response()})
    message = await client.step(request([ChatMessage(role="user", text="hi")]))
    assert message.text == "Sleeping."
    assert message.tool_calls[0].name == "schedule_next_wake"
    assert message.provider_raw and message.provider_raw[0]["model"] == "primary"


@pytest.mark.parametrize("error", [DAILY_QUOTA, BUSY])
async def test_falls_back_to_next_model_when_quota_used_or_busy(error: dict) -> None:
    code = error["error"]["code"]
    failure = genai_errors.ClientError(code, error) if code < 500 else genai_errors.ServerError(code, error)
    client, fake = client_with({"primary": failure, "backup": tool_call_response()})
    message = await client.step(request([ChatMessage(role="user", text="hi")]))
    assert [model for model, _ in fake.calls] == ["primary", "backup"]
    assert message.provider_raw and message.provider_raw[0]["model"] == "backup"


async def test_daily_quota_on_every_model_is_not_retryable() -> None:
    quota = genai_errors.ClientError(429, DAILY_QUOTA)
    client, _ = client_with({"primary": quota, "backup": quota})
    with pytest.raises(LLMError) as info:
        await client.step(request([ChatMessage(role="user", text="hi")]))
    assert info.value.retryable is False


async def test_invalid_key_does_not_try_other_models() -> None:
    client, fake = client_with({"primary": genai_errors.ClientError(400, BAD_KEY), "backup": tool_call_response()})
    with pytest.raises(LLMError) as info:
        await client.step(request([ChatMessage(role="user", text="hi")]))
    assert len(fake.calls) == 1
    assert info.value.retryable is False


async def test_replays_raw_content_only_for_the_model_that_produced_it() -> None:
    raw = {"model": "primary", "content": {"role": "model", "parts": [{"text": "raw", "thought_signature": "AP9z"}]}}
    previous = ChatMessage(role="assistant", text="neutral", tool_calls=[ToolCall(id="1", name="t", args={})], provider_raw=[raw])
    client, fake = client_with({"primary": genai_errors.ServerError(503, BUSY), "backup": tool_call_response()})
    await client.step(request([ChatMessage(role="user", text="hi"), previous]))

    primary_contents, backup_contents = fake.calls[0][1], fake.calls[1][1]
    assert primary_contents[1].parts[0].thought_signature is not None  # verbatim replay
    assert backup_contents[1].parts[0].text == "neutral"  # rebuilt without foreign signatures
    assert backup_contents[1].parts[0].thought_signature is None


def test_missing_api_key_fails_fast() -> None:
    with pytest.raises(LLMError):
        GeminiClient(api_key="", default_model="m")
