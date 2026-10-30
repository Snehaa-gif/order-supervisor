"""Tool catalogue for the supervisor agent.

Two kinds of tools:
- *Action tools* have side effects in the outside world (simulated here). They run as a
  Temporal activity with an idempotency key, so a retry never sends a message twice.
- *Control tools* change the supervisor's own state (sleep schedule, memory, wake guidance,
  closing the run). They are handled deterministically inside the workflow.
"""

from typing import Any

from app.domain import ToolSpec

SEND_CUSTOMER_MESSAGE = "send_customer_message"
CREATE_INTERNAL_NOTE = "create_internal_note"
ESCALATE_ISSUE = "escalate_issue"
MARK_ORDER_FOR_REVIEW = "mark_order_for_review"

SCHEDULE_NEXT_WAKE = "schedule_next_wake"
UPDATE_MEMORY = "update_memory"
SET_WAKE_GUIDANCE = "set_wake_guidance"
CLOSE_WORKFLOW = "close_workflow"

ACTION_TOOL_SPECS: dict[str, ToolSpec] = {
    SEND_CUSTOMER_MESSAGE: ToolSpec(
        name=SEND_CUSTOMER_MESSAGE,
        description="Send a message to the customer about their order (simulated email/SMS).",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The full message text the customer will read."},
                "channel": {"type": "string", "enum": ["email", "sms"], "description": "Delivery channel."},
            },
            "required": ["message", "channel"],
        },
    ),
    CREATE_INTERNAL_NOTE: ToolSpec(
        name=CREATE_INTERNAL_NOTE,
        description="Add an internal note on the order for the operations team. Not visible to the customer.",
        parameters={
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
        },
    ),
    ESCALATE_ISSUE: ToolSpec(
        name=ESCALATE_ISSUE,
        description="Escalate a problem with this order to a human team.",
        parameters={
            "type": "object",
            "properties": {
                "team": {"type": "string", "enum": ["payments", "logistics", "customer_support", "fraud"]},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "reason": {"type": "string"},
            },
            "required": ["team", "severity", "reason"],
        },
    ),
    MARK_ORDER_FOR_REVIEW: ToolSpec(
        name=MARK_ORDER_FOR_REVIEW,
        description="Flag the order for manual human review before anything else happens to it.",
        parameters={
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    ),
}

CONTROL_TOOL_SPECS: dict[str, ToolSpec] = {
    SCHEDULE_NEXT_WAKE: ToolSpec(
        name=SCHEDULE_NEXT_WAKE,
        description=(
            "Go to sleep and choose when to wake up for the next review. Call this once at the end of "
            "every turn unless you close the workflow. Important events can still wake you earlier."
        ),
        parameters={
            "type": "object",
            "properties": {
                "minutes": {"type": "integer", "description": "Minutes from now until the next review."},
                "reason": {"type": "string", "description": "What you want to check when you wake up."},
            },
            "required": ["minutes", "reason"],
        },
    ),
    UPDATE_MEMORY: ToolSpec(
        name=UPDATE_MEMORY,
        description=(
            "Replace your compact memory summary for this order. Keep it short: the current situation, "
            "open issues, promises made to the customer, and what to watch next."
        ),
        parameters={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    ),
    SET_WAKE_GUIDANCE: ToolSpec(
        name=SET_WAKE_GUIDANCE,
        description=(
            "Tune which future events should wake you immediately. Critical and terminal events always "
            "wake you; this only affects routine events."
        ),
        parameters={
            "type": "object",
            "properties": {
                "wake_on": {"type": "array", "items": {"type": "string"}, "description": "Event types to wake on."},
                "ignore": {"type": "array", "items": {"type": "string"}, "description": "Event types to defer."},
                "note": {"type": "string", "description": "Why you chose this guidance."},
            },
            "required": ["wake_on", "ignore", "note"],
        },
    ),
    CLOSE_WORKFLOW: ToolSpec(
        name=CLOSE_WORKFLOW,
        description="Close the supervision run because the order needs no further oversight.",
        parameters={
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    ),
}

ALL_ACTION_TOOLS: tuple[str, ...] = tuple(ACTION_TOOL_SPECS)


def tool_specs_for(enabled_action_tools: list[str]) -> list[ToolSpec]:
    """Tools offered to the model: the supervisor's enabled action tools plus every control tool."""
    actions = [ACTION_TOOL_SPECS[name] for name in enabled_action_tools if name in ACTION_TOOL_SPECS]
    return [*actions, *CONTROL_TOOL_SPECS.values()]


def is_control_tool(name: str) -> bool:
    return name in CONTROL_TOOL_SPECS


def validate_args(spec: ToolSpec, args: dict[str, Any]) -> str | None:
    """Minimal argument check against the tool schema. Returns an error message or None."""
    missing = [key for key in spec.parameters.get("required", []) if args.get(key) in (None, "")]
    if missing:
        return f"Missing required argument(s): {', '.join(missing)}"
    for key, prop in spec.parameters.get("properties", {}).items():
        allowed = prop.get("enum")
        if allowed and key in args and args[key] not in allowed:
            return f"Invalid value for '{key}': {args[key]!r}. Allowed: {', '.join(allowed)}"
    return None
