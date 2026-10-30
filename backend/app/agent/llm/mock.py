"""Deterministic rule-based stand-in for an LLM.

Used by the test suite and for running the whole system offline (LLM_PROVIDER=mock).
It reads the same turn prompt the real model gets and answers with sensible tool calls,
so every workflow path can be exercised without network access or API quota.
"""

import re
from typing import Any

from app.agent import tools as t
from app.domain import AgentStepInput, ChatMessage, ToolCall

EVENT_RULES: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "payment_failed": [
        (
            t.SEND_CUSTOMER_MESSAGE,
            {
                "channel": "email",
                "message": "Your payment did not go through. Please update your payment method so we can ship your order.",
            },
        ),
        (t.ESCALATE_ISSUE, {"team": "payments", "severity": "medium", "reason": "Payment failed for this order."}),
    ],
    "shipment_delayed": [
        (t.CREATE_INTERNAL_NOTE, {"note": "Carrier reported a delay. Monitoring closely."}),
        (
            t.SEND_CUSTOMER_MESSAGE,
            {"channel": "email", "message": "Your shipment is running late. We are tracking it and will update you."},
        ),
    ],
    "refund_requested": [
        (t.MARK_ORDER_FOR_REVIEW, {"reason": "Customer requested a refund."}),
        (t.ESCALATE_ISSUE, {"team": "customer_support", "severity": "medium", "reason": "Refund request needs approval."}),
    ],
    "customer_message_received": [
        (
            t.SEND_CUSTOMER_MESSAGE,
            {
                "channel": "email",
                "message": "Thanks for reaching out. We are looking into your order and will follow up shortly.",
            },
        ),
    ],
    "no_update_for_n_hours": [
        (t.ESCALATE_ISSUE, {"team": "logistics", "severity": "low", "reason": "Order has had no updates for a long time."}),
    ],
}


class MockLLMClient:
    name = "mock"

    async def step(self, request: AgentStepInput) -> ChatMessage:
        last = request.messages[-1]
        if last.role == "tool":
            return ChatMessage(role="assistant", text="Handled the situation with the tools above and scheduled my next review.")

        enabled = {spec.name for spec in request.tools}
        prompt = last.text
        calls = [c for c in self._plan(prompt) if c[0] in enabled]
        tool_calls = [ToolCall(id=f"mock-{i}", name=name, args=args) for i, (name, args) in enumerate(calls)]
        return ChatMessage(role="assistant", text="", tool_calls=tool_calls)

    async def complete_text(self, model: str | None, prompt: str) -> str:
        lines = [line[2:] for line in prompt.splitlines() if line.startswith("- [")]
        return "Compacted history: " + " | ".join(line.split("] ", 1)[-1] for line in lines[-6:])

    async def complete_json(self, model: str | None, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        status = re.search(r"final status: (\w+)", prompt)
        return {
            "summary": "The supervisor monitored the order through its lifecycle and handled the events it saw.",
            "outcome": f"Order ended as {status.group(1) if status else 'unknown'}",
            "key_actions": [line[2:] for line in prompt.splitlines() if line.startswith("- ") and ":" in line][:5],
            "learnings": ["Rule-based mock provider: connect a real LLM for genuine learnings."],
            "recommendations": ["Set LLM_PROVIDER=gemini with a GEMINI_API_KEY for real analysis."],
        }

    def _plan(self, prompt: str) -> list[tuple[str, dict[str, Any]]]:
        new_events = _section(prompt, "New events since your last turn")
        plan: list[tuple[str, dict[str, Any]]] = []

        if "terminal state" in prompt:
            plan.append((t.CREATE_INTERNAL_NOTE, {"note": "Order reached a terminal state; closing supervision."}))
            plan.append((t.CLOSE_WORKFLOW, {"reason": "Order reached a terminal state."}))
            return plan

        for event_type, actions in EVENT_RULES.items():
            if event_type in new_events:
                plan.extend(actions)

        unknown = re.findall(r"\] ([a-z_]+) ", new_events)
        if any(e not in EVENT_RULES and e not in _ROUTINE for e in unknown):
            plan.append(
                (
                    t.ESCALATE_ISSUE,
                    {"team": "customer_support", "severity": "medium", "reason": "Unrecognised event type received."},
                )
            )

        if "supervision run just started" in prompt:
            plan.append(
                (
                    t.SET_WAKE_GUIDANCE,
                    {
                        "wake_on": [],
                        "ignore": ["payment_confirmed"],
                        "note": "Routine payment confirmations need no immediate action.",
                    },
                )
            )

        plan.append(
            (
                t.UPDATE_MEMORY,
                {
                    "summary": f"Order status: {_order_status(prompt)}. Last turn handled: {new_events.strip()[:200] or 'routine check'}."
                },
            )
        )
        plan.append((t.SCHEDULE_NEXT_WAKE, {"minutes": 5, "reason": "Routine follow-up check."}))
        return plan


_ROUTINE = {
    "order_created",
    "payment_confirmed",
    "shipment_created",
    "out_for_delivery",
    "delivered",
    "refund_completed",
    "order_cancelled",
}


def _section(prompt: str, heading: str) -> str:
    match = re.search(rf"# {re.escape(heading)}\n(.*?)(?:\n# |\Z)", prompt, re.S)
    return match.group(1) if match else ""


def _order_status(prompt: str) -> str:
    match = re.search(r"Current status: (\S+)", prompt)
    return match.group(1) if match else "unknown"
