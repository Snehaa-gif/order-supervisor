"""Domain models shared by the API, the Temporal workflow and its activities.

Everything that crosses the workflow/activity boundary is a frozen Pydantic model so it
serializes cleanly through Temporal's pydantic data converter and can't be mutated by accident.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


# --- Order events -------------------------------------------------------------------------------


class EventType(StrEnum):
    ORDER_CREATED = "order_created"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_FAILED = "payment_failed"
    SHIPMENT_CREATED = "shipment_created"
    SHIPMENT_DELAYED = "shipment_delayed"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    REFUND_REQUESTED = "refund_requested"
    REFUND_COMPLETED = "refund_completed"
    ORDER_CANCELLED = "order_cancelled"
    CUSTOMER_MESSAGE_RECEIVED = "customer_message_received"
    NO_UPDATE_FOR_N_HOURS = "no_update_for_n_hours"


KNOWN_EVENT_TYPES: frozenset[str] = frozenset(e.value for e in EventType)

# Events after which the order lifecycle is over and the supervisor wraps up.
TERMINAL_EVENT_TYPES: frozenset[str] = frozenset({EventType.DELIVERED, EventType.REFUND_COMPLETED, EventType.ORDER_CANCELLED})

# Order status implied by each event (unknown / informational events leave status unchanged).
EVENT_TO_ORDER_STATUS: dict[str, str] = {
    EventType.ORDER_CREATED: "created",
    EventType.PAYMENT_CONFIRMED: "paid",
    EventType.PAYMENT_FAILED: "payment_failed",
    EventType.SHIPMENT_CREATED: "shipped",
    EventType.SHIPMENT_DELAYED: "delayed",
    EventType.OUT_FOR_DELIVERY: "out_for_delivery",
    EventType.DELIVERED: "delivered",
    EventType.REFUND_REQUESTED: "refund_requested",
    EventType.REFUND_COMPLETED: "refunded",
    EventType.ORDER_CANCELLED: "cancelled",
}


class OrderEvent(Frozen):
    """An event about the order, delivered to the workflow as a signal.

    `type` is a free string on purpose: unknown event types must reach the workflow so the
    supervisor can escalate them instead of the API silently rejecting them.
    """

    id: str
    type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
    source: str = "api"


# --- Supervisor configuration -------------------------------------------------------------------


class WakeAggressiveness(StrEnum):
    LOW = "low"  # only critical events wake the agent
    BALANCED = "balanced"  # critical events + stale orders
    HIGH = "high"  # every event wakes the agent


class SupervisorConfig(Frozen):
    id: str
    name: str
    base_instruction: str
    tools: list[str]
    default_wake_minutes: int = Field(ge=1, le=24 * 60)
    max_sleep_minutes: int = Field(ge=1, le=7 * 24 * 60)
    wake_aggressiveness: WakeAggressiveness = WakeAggressiveness.BALANCED
    model: str | None = None


# --- Workflow input / state ---------------------------------------------------------------------


class RunInput(Frozen):
    run_id: str
    order_id: str
    order_context: dict[str, Any]
    supervisor: SupervisorConfig
    instructions: list[str] = Field(default_factory=list)
    # History size (in events) after which the workflow continues-as-new to stay lean.
    max_history_events: int = 2000
    # Populated only when the workflow continues-as-new and carries its state forward.
    carried_state: "CarriedState | None" = None


class WakeGuidance(Frozen):
    """Agent-authored hints that tune the wake-up classifier for this run."""

    wake_on: list[str] = Field(default_factory=list)
    ignore: list[str] = Field(default_factory=list)
    note: str = ""


class MemoryItem(Frozen):
    at: datetime
    text: str


class CarriedState(Frozen):
    order_status: str
    memory_summary: str
    recent: list[MemoryItem]
    unseen_events: list[OrderEvent]
    wake_guidance: WakeGuidance
    instructions: list[str]
    next_wake_at: datetime | None
    paused: bool
    turn_count: int
    actions_taken: list[str]
    generation: int
    inbox: list[OrderEvent] = Field(default_factory=list)
    pending_wake: "PendingWake | None" = None


class PendingWake(Frozen):
    trigger: "WakeTrigger"
    note: str = ""


class InstructionSignal(Frozen):
    text: str = Field(min_length=1, max_length=1000)
    wake_agent: bool = False


RunStatus = Literal["starting", "awake", "sleeping", "paused", "completing", "completed", "terminated", "failed"]


class RunSnapshot(Frozen):
    """What the workflow persists to the database for the UI after every state change."""

    run_id: str
    status: RunStatus
    order_status: str
    memory_summary: str
    next_wake_at: datetime | None
    wake_guidance: WakeGuidance
    instructions: list[str]
    turn_count: int
    pending_events: int


# --- Timeline -----------------------------------------------------------------------------------

TimelineKind = Literal[
    "event",  # an order event arrived
    "classification",  # the wake-up policy decided what to do with it
    "wake",  # the agent woke up (and why)
    "agent",  # the agent's reasoning / turn summary
    "tool",  # a tool call and its result
    "sleep",  # the agent went to sleep
    "instruction",  # a human added a run-specific instruction
    "control",  # pause / resume / interrupt / terminate
    "memory",  # memory was updated or compacted
    "system",  # workflow lifecycle (started, continued-as-new, closed, errors)
]


class TimelineEntry(Frozen):
    run_id: str
    at: datetime
    kind: TimelineKind
    title: str
    detail: dict[str, Any] = Field(default_factory=dict)
    important: bool = False


# --- Agent / LLM --------------------------------------------------------------------------------

WakeTrigger = Literal["workflow_start", "event", "scheduled", "manual", "terminal"]


class ToolCall(Frozen):
    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResult(Frozen):
    call_id: str
    name: str
    ok: bool
    output: dict[str, Any]


class ChatMessage(Frozen):
    """Provider-neutral conversation message.

    `provider_raw` keeps the provider's native representation of a model message (e.g. Gemini
    parts with thought signatures) so multi-step tool use can be replayed exactly.
    """

    role: Literal["user", "assistant", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    provider_raw: list[dict[str, Any]] | None = None


class ToolSpec(Frozen):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema


class AgentStepInput(Frozen):
    model: str | None
    system_prompt: str
    messages: list[ChatMessage]
    tools: list[ToolSpec]


class AgentStepOutput(Frozen):
    message: ChatMessage


class ExecuteToolInput(Frozen):
    run_id: str
    order_id: str
    idempotency_key: str
    call: ToolCall


class CompactMemoryInput(Frozen):
    model: str | None
    memory_summary: str
    items: list[MemoryItem]


class FinalReport(Frozen):
    summary: str
    key_actions: list[str]
    learnings: list[str]
    recommendations: list[str]
    outcome: str


class FinalReportInput(Frozen):
    run_id: str
    model: str | None
    order_id: str
    order_context: dict[str, Any]
    order_status: str
    close_reason: str
    memory_summary: str
    recent: list[MemoryItem]
    actions_taken: list[str]
    instructions: list[str]


PendingWake.model_rebuild()
CarriedState.model_rebuild()
RunInput.model_rebuild()
