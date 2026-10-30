"""Google Gemini implementation of the LLM interface (works on the free tier)."""

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.agent.llm.base import LLMError
from app.domain import AgentStepInput, ChatMessage, ToolCall, ToolSpec

# HTTP status codes worth retrying: rate limits and transient server errors.
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
# Errors that are specific to one model (busy, or its quota is used up): try the next model.
FALLBACK_STATUS = frozenset({429, 503, 504})
REQUEST_TIMEOUT_MS = 20_000

Contents = Any  # what google-genai accepts as `contents`


class GeminiClient:
    name = "gemini"

    def __init__(self, api_key: str, default_model: str, fallback_models: list[str] | None = None) -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set (see backend/.env).", retryable=False)
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
        self._default_model = default_model
        self._fallback_models = fallback_models or []

    async def step(self, request: AgentStepInput) -> ChatMessage:
        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            tools=[types.Tool(function_declarations=[_declaration(spec) for spec in request.tools])],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.2,
        )
        response, model = await self._generate(
            request.model, lambda target: [_to_content(m, target) for m in request.messages], config
        )
        return _to_message(response, model)

    async def complete_text(self, model: str | None, prompt: str) -> str:
        config = types.GenerateContentConfig(temperature=0.2)
        response, _ = await self._generate(model, lambda _target: prompt, config)
        text = (response.text or "").strip()
        if not text:
            raise LLMError("Gemini returned an empty response.", retryable=True)
        return text

    async def complete_json(self, model: str | None, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        config = types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        response, _ = await self._generate(model, lambda _target: prompt, config)
        try:
            parsed = json.loads(response.text or "")
        except json.JSONDecodeError as exc:
            raise LLMError(f"Gemini returned invalid JSON: {exc}", retryable=True) from exc
        if not isinstance(parsed, dict):
            raise LLMError("Gemini returned JSON that is not an object.", retryable=True)
        return parsed

    async def _generate(
        self,
        model: str | None,
        contents_for: Callable[[str], Contents],
        config: types.GenerateContentConfig,
    ) -> tuple[types.GenerateContentResponse, str]:
        """Call the model, falling back to the next one when it is busy or out of quota."""
        candidates = list(dict.fromkeys([model or self._default_model, *self._fallback_models]))
        last_error: genai_errors.APIError | None = None
        network_error: httpx.HTTPError | None = None
        for candidate in candidates:
            try:
                response = await self._client.aio.models.generate_content(
                    model=candidate, contents=contents_for(candidate), config=config
                )
                return response, candidate
            except genai_errors.APIError as exc:
                last_error = exc
                if exc.code not in FALLBACK_STATUS:
                    break
            except httpx.HTTPError as exc:  # timeouts / connection drops: try the next model
                network_error = exc
        if last_error is None:
            raise LLMError(f"Could not reach Gemini: {network_error!r}", retryable=True) from network_error
        raise LLMError(
            f"Gemini API error {last_error.code}: {last_error.message}",
            # A used-up *daily* quota will not recover within Temporal's retry window.
            retryable=last_error.code in RETRYABLE_STATUS and not _is_daily_quota(last_error),
        ) from last_error


def _declaration(spec: ToolSpec) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(name=spec.name, description=spec.description, parameters_json_schema=spec.parameters)


def _is_daily_quota(error: genai_errors.APIError) -> bool:
    return error.code == 429 and "PerDay" in json.dumps(error.details, default=str)


def _to_content(message: ChatMessage, target_model: str) -> types.Content:
    raw = message.provider_raw[0] if message.provider_raw else None
    if message.role == "assistant" and raw and raw.get("model") == target_model:
        # Same model: replay its content verbatim so thought signatures stay intact.
        return types.Content.model_validate(raw["content"])
    if message.role == "assistant":
        parts = [types.Part(text=message.text)] if message.text else []
        parts += [types.Part(function_call=types.FunctionCall(name=c.name, args=c.args)) for c in message.tool_calls]
        return types.Content(role="model", parts=parts)
    if message.role == "tool":
        return types.Content(
            role="user",
            parts=[
                types.Part(function_response=types.FunctionResponse(name=r.name, response=r.output)) for r in message.tool_results
            ],
        )
    return types.Content(role="user", parts=[types.Part(text=message.text)])


def _to_message(response: types.GenerateContentResponse, model: str) -> ChatMessage:
    candidate = response.candidates[0] if response.candidates else None
    if candidate is None or candidate.content is None or not candidate.content.parts:
        reason = candidate.finish_reason if candidate else "no candidates"
        raise LLMError(f"Gemini returned no content (finish reason: {reason}).", retryable=True)

    content = candidate.content
    texts = [p.text for p in content.parts if p.text and not p.thought]
    calls = [
        ToolCall(id=p.function_call.id or uuid.uuid4().hex[:12], name=p.function_call.name or "", args=p.function_call.args or {})
        for p in content.parts
        if p.function_call
    ]
    return ChatMessage(
        role="assistant",
        text="\n".join(texts).strip(),
        tool_calls=calls,
        provider_raw=[{"model": model, "content": content.model_dump(mode="json", exclude_none=True)}],
    )
