from datetime import UTC, datetime

import pytest

from app.agent.classifier import classify_event
from app.domain import OrderEvent, WakeAggressiveness, WakeGuidance

pytestmark = pytest.mark.unit

BALANCED = WakeAggressiveness.BALANCED
NO_GUIDANCE = WakeGuidance()


def event(event_type: str, **payload: object) -> OrderEvent:
    return OrderEvent(id="e", type=event_type, payload=payload, occurred_at=datetime(2026, 1, 1, tzinfo=UTC))


@pytest.mark.parametrize("event_type", ["payment_failed", "shipment_delayed", "refund_requested", "customer_message_received"])
def test_critical_events_always_wake(event_type: str) -> None:
    result = classify_event(event(event_type), WakeAggressiveness.LOW, WakeGuidance(ignore=[event_type]))
    assert result.wakes


@pytest.mark.parametrize("event_type", ["delivered", "order_cancelled", "refund_completed"])
def test_terminal_events_wake(event_type: str) -> None:
    assert classify_event(event(event_type), WakeAggressiveness.LOW, NO_GUIDANCE).wakes


def test_routine_event_is_deferred_when_balanced() -> None:
    result = classify_event(event("payment_confirmed"), BALANCED, NO_GUIDANCE)
    assert result.decision == "defer"


def test_routine_event_wakes_when_aggressiveness_high() -> None:
    assert classify_event(event("shipment_created"), WakeAggressiveness.HIGH, NO_GUIDANCE).wakes


def test_agent_guidance_can_request_wake_for_routine_event() -> None:
    result = classify_event(event("shipment_created"), BALANCED, WakeGuidance(wake_on=["shipment_created"]))
    assert result.wakes
    assert "Agent asked" in result.reason


def test_agent_guidance_can_silence_routine_event_even_when_high() -> None:
    result = classify_event(event("out_for_delivery"), WakeAggressiveness.HIGH, WakeGuidance(ignore=["out_for_delivery"]))
    assert result.decision == "defer"


def test_unknown_event_wakes_and_is_flagged() -> None:
    result = classify_event(event("warehouse_fire"), WakeAggressiveness.LOW, NO_GUIDANCE)
    assert result.wakes
    assert result.unknown_event


@pytest.mark.parametrize(
    ("hours", "level", "wakes"),
    [
        (30, WakeAggressiveness.BALANCED, True),
        (10, WakeAggressiveness.BALANCED, False),
        (10, WakeAggressiveness.HIGH, True),
        (30, WakeAggressiveness.LOW, False),
        ("50", WakeAggressiveness.LOW, True),
    ],
)
def test_stale_order_threshold_depends_on_aggressiveness(hours: object, level: WakeAggressiveness, wakes: bool) -> None:
    assert classify_event(event("no_update_for_n_hours", hours=hours), level, NO_GUIDANCE).wakes is wakes


def test_stale_order_without_duration_wakes() -> None:
    assert classify_event(event("no_update_for_n_hours", hours="soon"), BALANCED, NO_GUIDANCE).wakes
