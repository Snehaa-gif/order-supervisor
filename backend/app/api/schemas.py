"""Request/response models for the HTTP API."""

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.agent.tools import ALL_ACTION_TOOLS
from app.domain import WakeAggressiveness


def _as_utc(value: datetime) -> datetime:
    """Some databases (SQLite) drop the timezone; all stored times are UTC, so say so explicitly."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]

MAX_JSON_BYTES = 8_000  # keeps signal payloads and workflow history small


def _bounded_json(value: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(value, default=str)) > MAX_JSON_BYTES:
        raise ValueError(f"must serialize to at most {MAX_JSON_BYTES} bytes of JSON")
    return value


def _stripped(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


BoundedJson = Annotated[dict[str, Any], AfterValidator(_bounded_json)]
InstructionText = Annotated[str, Field(max_length=1000), AfterValidator(_stripped)]


class SupervisorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_instruction: str = Field(min_length=10, max_length=4000)
    tools: list[str] = Field(min_length=1)
    default_wake_minutes: int = Field(default=5, ge=1, le=24 * 60)
    max_sleep_minutes: int = Field(default=60, ge=1, le=7 * 24 * 60)
    wake_aggressiveness: WakeAggressiveness = WakeAggressiveness.BALANCED
    model: str | None = Field(default=None, max_length=80)

    @field_validator("tools")
    @classmethod
    def known_tools(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(ALL_ACTION_TOOLS))
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(unknown)}")
        return list(dict.fromkeys(value))

    @field_validator("model")
    @classmethod
    def blank_model_is_default(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class SupervisorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_instruction: str
    tools: list[str]
    default_wake_minutes: int
    max_sleep_minutes: int
    wake_aggressiveness: str
    model: str | None
    is_template: bool
    created_at: UtcDatetime


class RunCreate(BaseModel):
    supervisor_id: str
    order_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    order_context: BoundedJson = Field(default_factory=dict)
    instructions: list[Annotated[str, Field(max_length=1000)]] = Field(default_factory=list, max_length=20)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    supervisor_id: str
    supervisor_name: str
    workflow_id: str
    status: str
    order_status: str
    order_context: dict[str, Any]
    memory_summary: str
    next_wake_at: UtcDatetime | None
    wake_guidance: dict[str, Any]
    instructions: list[str]
    turn_count: int
    pending_events: int
    final_report: dict[str, Any] | None
    close_reason: str | None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    closed_at: UtcDatetime | None


class TimelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    at: UtcDatetime
    kind: str
    title: str
    detail: dict[str, Any]
    important: bool


class ToolExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tool: str
    args: dict[str, Any]
    result: dict[str, Any]
    created_at: UtcDatetime


class RunDetail(RunOut):
    timeline: list[TimelineOut]
    tool_executions: list[ToolExecutionOut]


class EventIn(BaseModel):
    type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    payload: BoundedJson = Field(default_factory=dict)
    source: str = Field(default="ui", max_length=32)


class InstructionIn(BaseModel):
    text: InstructionText
    wake_agent: bool = False


class InterruptIn(BaseModel):
    note: str = Field(default="", max_length=500)


class TerminateIn(BaseModel):
    reason: str = Field(default="Terminated by operator", max_length=500)


class Accepted(BaseModel):
    ok: bool = True
    message: str
