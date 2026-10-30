"""Wake-up policy: decides whether an incoming event should wake the main agent right now.

This is deliberately a small, deterministic rule set rather than an LLM call:
it runs inside the Temporal workflow (so it must be deterministic), it costs nothing,
and its decisions are easy to explain in the timeline. The agent can tune it per run
through `set_wake_guidance`.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain import (
    KNOWN_EVENT_TYPES,
    TERMINAL_EVENT_TYPES,
    EventType,
    OrderEvent,
    WakeAggressiveness,
    WakeGuidance,
)

Decision = Literal["wake_now", "defer"]

# Events that always need a decision from the agent, whatever the configuration says.
CRITICAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        EventType.PAYMENT_FAILED,
        EventType.SHIPMENT_DELAYED,
        EventType.REFUND_REQUESTED,
        EventType.CUSTOMER_MESSAGE_RECEIVED,
    }
)

# How many hours of silence count as "stale" for each aggressiveness level.
STALE_HOURS_THRESHOLD: dict[WakeAggressiveness, int] = {
    WakeAggressiveness.LOW: 48,
    WakeAggressiveness.BALANCED: 24,
    WakeAggressiveness.HIGH: 6,
}


class Classification(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: Decision
    reason: str
    unknown_event: bool = False

    @property
    def wakes(self) -> bool:
        return self.decision == "wake_now"


def classify_event(
    event: OrderEvent,
    aggressiveness: WakeAggressiveness,
    guidance: WakeGuidance,
) -> Classification:
    """Return whether `event` should wake the agent now or wait for the next scheduled wake-up."""
    event_type = event.type

    if event_type in TERMINAL_EVENT_TYPES:
        return Classification(decision="wake_now", reason="Terminal event: the order lifecycle is ending.")

    if event_type not in KNOWN_EVENT_TYPES:
        return Classification(
            decision="wake_now",
            reason=f"Unknown event type '{event_type}': the agent must assess and escalate if unclear.",
            unknown_event=True,
        )

    if event_type in CRITICAL_EVENT_TYPES:
        return Classification(decision="wake_now", reason="Critical event: needs a decision now.")

    if event_type in guidance.wake_on:
        return Classification(decision="wake_now", reason="Agent asked to be woken for this event type.")

    if event_type in guidance.ignore:
        return Classification(decision="defer", reason="Agent asked not to be woken for this event type.")

    if event_type == EventType.NO_UPDATE_FOR_N_HOURS:
        return _classify_stale(event, aggressiveness)

    if aggressiveness == WakeAggressiveness.HIGH:
        return Classification(decision="wake_now", reason="High aggressiveness: every event wakes the agent.")

    return Classification(decision="defer", reason="Routine progress; reviewed at the next scheduled wake-up.")


def _classify_stale(event: OrderEvent, aggressiveness: WakeAggressiveness) -> Classification:
    threshold = STALE_HOURS_THRESHOLD[aggressiveness]
    hours = _as_number(event.payload.get("hours"))
    if hours is None:
        return Classification(decision="wake_now", reason="Order has gone quiet (duration unknown).")
    if hours >= threshold:
        return Classification(decision="wake_now", reason=f"No update for {hours:g}h (threshold {threshold}h).")
    return Classification(decision="defer", reason=f"No update for {hours:g}h, below the {threshold}h threshold.")


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
