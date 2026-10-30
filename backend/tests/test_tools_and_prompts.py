from datetime import UTC, datetime

import pytest

from app.agent import prompts
from app.agent import tools as t
from app.db.session import normalize_database_url
from app.domain import MemoryItem, OrderEvent, WakeGuidance
from app.templates import TEMPLATES

pytestmark = pytest.mark.unit


def test_specs_include_enabled_actions_and_all_control_tools() -> None:
    names = [spec.name for spec in t.tool_specs_for([t.CREATE_INTERNAL_NOTE])]
    assert t.CREATE_INTERNAL_NOTE in names
    assert t.SEND_CUSTOMER_MESSAGE not in names
    assert set(t.CONTROL_TOOL_SPECS) <= set(names)


def test_at_least_four_action_tools_exist() -> None:
    assert len(t.ALL_ACTION_TOOLS) >= 4


def test_validate_args_reports_missing_and_invalid_enum() -> None:
    spec = t.ACTION_TOOL_SPECS[t.ESCALATE_ISSUE]
    assert "Missing" in (t.validate_args(spec, {"team": "payments"}) or "")
    assert "Invalid value" in (t.validate_args(spec, {"team": "nobody", "severity": "low", "reason": "x"}) or "")
    assert t.validate_args(spec, {"team": "payments", "severity": "low", "reason": "x"}) is None


def test_system_prompt_contains_run_instructions() -> None:
    prompt = prompts.build_system_prompt(TEMPLATES[0], ["Escalate delays immediately"])
    assert "Escalate delays immediately" in prompt
    assert TEMPLATES[0].name in prompt


def test_turn_prompt_lists_new_events_and_memory() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    prompt = prompts.build_turn_prompt(
        trigger="event",
        trigger_note="payment_failed",
        now=now,
        order_id="ORD-1",
        order_status="payment_failed",
        order_context={"customer": "Asha"},
        memory_summary="Customer is a repeat buyer.",
        recent=[MemoryItem(at=now, text="Event order_created")],
        new_events=[OrderEvent(id="e", type="payment_failed", payload={"reason": "declined"}, occurred_at=now)],
        actions_taken=["Internal note: hello"],
        wake_guidance=WakeGuidance(),
    )
    assert "payment_failed" in prompt
    assert "Customer is a repeat buyer." in prompt
    assert "Internal note: hello" in prompt


@pytest.mark.parametrize(
    ("raw", "expected_prefix", "ssl"),
    [
        ("postgresql://u:p@aws-0-ap-south-1.pooler.supabase.com:5432/postgres", "postgresql+asyncpg://", True),
        ("postgres://u:p@localhost:5432/db", "postgresql+asyncpg://", False),
        ("sqlite+aiosqlite:///./x.db", "sqlite+aiosqlite://", False),
    ],
)
def test_normalize_database_url(raw: str, expected_prefix: str, ssl: bool) -> None:
    url, connect_args = normalize_database_url(raw)
    assert url.startswith(expected_prefix)
    assert ("ssl" in connect_args) is ssl


def test_supabase_pooler_disables_statement_cache() -> None:
    _, connect_args = normalize_database_url("postgresql://u:p@aws-0-ap-south-1.pooler.supabase.com:5432/postgres")
    assert connect_args["statement_cache_size"] == 0
