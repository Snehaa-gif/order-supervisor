"""Prompt builders. Pure functions: they run inside the workflow, so no I/O and no clock reads."""

import json
from datetime import datetime
from typing import Any

from app.domain import MemoryItem, OrderEvent, SupervisorConfig, WakeGuidance, WakeTrigger

SYSTEM_PROMPT_TEMPLATE = """You are "{name}", an AI supervisor that oversees ONE e-commerce order from creation until completion.

## Your job
{base_instruction}

## How you operate
- You are not running continuously. You are woken up for a short turn when the run starts, when an important event arrives, at the time you scheduled, or when a human asks for a review.
- In each turn: read the situation, decide whether anything needs doing, use action tools only when they add value, then go back to sleep.
- End EVERY turn with exactly one of: `schedule_next_wake` (choose minutes until your next review, between 1 and {max_sleep}) or `close_workflow`. If you do neither, you will be woken again in {default_wake} minutes.
- Use `update_memory` whenever the situation changes, so your future self knows what happened, what was promised, and what is still open. Keep it under 120 words.
- Use `set_wake_guidance` if routine events should (or should not) wake you for this particular order.
- Never invent facts about the order. Never promise refunds, discounts or dates you cannot see in the context.
- If an event type is unfamiliar, assess it; if you cannot tell whether it is harmful, escalate it.
- Do not repeat an action you have already taken (check "Actions already taken") unless the situation has changed.
- Explain your reasoning in one or two sentences as text in the SAME reply as your tool calls.
- Your turn ends as soon as `schedule_next_wake` or `close_workflow` succeeds, so make all other calls (actions, memory updates) in that same reply or before it.

## Run-specific instructions from humans (these override the defaults above)
{instructions}
"""

TRIGGER_DESCRIPTIONS: dict[WakeTrigger, str] = {
    "workflow_start": "The supervision run just started. Get oriented, set up your memory and plan your first check-in.",
    "event": "You were woken because an important event arrived.",
    "scheduled": "Your scheduled wake-up time arrived. Review the order's progress.",
    "manual": "A human operator interrupted your sleep and asked for an immediate review.",
    "terminal": (
        "The order has reached a terminal state. Take any final actions that are genuinely needed, then call `close_workflow`."
    ),
}


def build_system_prompt(supervisor: SupervisorConfig, instructions: list[str]) -> str:
    rendered = "\n".join(f"- {text}" for text in instructions) if instructions else "- (none)"
    return SYSTEM_PROMPT_TEMPLATE.format(
        name=supervisor.name,
        base_instruction=supervisor.base_instruction.strip(),
        max_sleep=supervisor.max_sleep_minutes,
        default_wake=supervisor.default_wake_minutes,
        instructions=rendered,
    )


def build_turn_prompt(
    *,
    trigger: WakeTrigger,
    trigger_note: str,
    now: datetime,
    order_id: str,
    order_status: str,
    order_context: dict[str, Any],
    memory_summary: str,
    recent: list[MemoryItem],
    new_events: list[OrderEvent],
    actions_taken: list[str],
    wake_guidance: WakeGuidance,
) -> str:
    sections = [
        f"# Wake-up reason\n{TRIGGER_DESCRIPTIONS[trigger]}" + (f"\nDetail: {trigger_note}" if trigger_note else ""),
        f"# Current time\n{now.isoformat(timespec='seconds')}",
        f"# Order\nID: {order_id}\nCurrent status: {order_status}\nContext: {json.dumps(order_context, default=str)}",
        f"# Your memory summary\n{memory_summary or '(empty - this is your first turn)'}",
        "# Recent important history (oldest first)\n" + _render_items(recent),
        "# New events since your last turn\n" + _render_events(new_events),
        "# Actions already taken in this run\n" + ("\n".join(f"- {a}" for a in actions_taken) or "(none yet)"),
        "# Current wake guidance\n"
        + f"wake_on={wake_guidance.wake_on or '[]'} ignore={wake_guidance.ignore or '[]'}"
        + (f" ({wake_guidance.note})" if wake_guidance.note else ""),
    ]
    return "\n\n".join(sections)


def build_compaction_prompt(memory_summary: str, items: list[MemoryItem]) -> str:
    return (
        "You maintain the long-term memory of an AI order supervisor. Merge the older history below into the "
        "existing summary. Keep facts that still matter (problems, promises to the customer, escalations, "
        "decisions and their reasons). Drop routine noise. Reply with the new summary only, under 120 words.\n\n"
        f"## Existing summary\n{memory_summary or '(empty)'}\n\n## Older history to fold in\n{_render_items(items)}"
    )


def build_final_report_prompt(
    *,
    order_id: str,
    order_context: dict[str, Any],
    order_status: str,
    close_reason: str,
    memory_summary: str,
    recent: list[MemoryItem],
    actions_taken: list[str],
    instructions: list[str],
) -> str:
    return (
        "The supervision run for this order has ended. Write the end-of-run report as JSON with keys: "
        '"summary" (3-5 sentences), "outcome" (one short phrase), "key_actions" (list of the important actions '
        'taken and why), "learnings" (list: what this order taught us about the process), and '
        '"recommendations" (list: concrete feedback to improve operations or the supervisor itself).\n\n'
        f"Order {order_id}, final status: {order_status}. Run closed because: {close_reason}\n"
        f"Order context: {json.dumps(order_context, default=str)}\n\n"
        f"## Memory summary\n{memory_summary or '(empty)'}\n\n"
        f"## Recent history\n{_render_items(recent)}\n\n"
        "## Actions taken\n" + ("\n".join(f"- {a}" for a in actions_taken) or "(none)") + "\n\n"
        "## Human instructions during the run\n" + ("\n".join(f"- {i}" for i in instructions) or "(none)")
    )


def _render_items(items: list[MemoryItem]) -> str:
    if not items:
        return "(nothing yet)"
    return "\n".join(f"- [{item.at.isoformat(timespec='seconds')}] {item.text}" for item in items)


def _render_events(events: list[OrderEvent]) -> str:
    if not events:
        return "(none)"
    return "\n".join(
        f"- [{e.occurred_at.isoformat(timespec='seconds')}] {e.type} {json.dumps(e.payload, default=str)}" for e in events
    )
