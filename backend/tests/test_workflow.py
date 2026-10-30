"""End-to-end workflow tests on Temporal's time-skipping test server (real workflow + real activities,
mock LLM, SQLite database)."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import WorkflowHandle
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker

from app.agent.llm.base import LLMError
from app.agent.llm.mock import MockLLMClient
from app.db import repository as repo
from app.domain import (
    AgentStepInput,
    ChatMessage,
    ExecuteToolInput,
    FinalReport,
    InstructionSignal,
    OrderEvent,
    RunInput,
    RunSnapshot,
    ToolCall,
)
from app.templates import TEMPLATES
from app.workflows.activities import SupervisorActivities
from app.workflows.order_supervisor import OrderSupervisorWorkflow

pytestmark = pytest.mark.integration

SUPERVISOR = TEMPLATES[0]  # balanced, default wake 5 min, all tools


@pytest.fixture(scope="session")
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    yield environment
    await environment.shutdown()


class FailingLLM(MockLLMClient):
    """Simulates a broken LLM provider (e.g. invalid API key)."""

    name = "failing"

    async def step(self, request: AgentStepInput) -> ChatMessage:
        raise LLMError("invalid API key", retryable=False)

    async def complete_text(self, model: str | None, prompt: str) -> str:
        raise LLMError("invalid API key", retryable=False)

    async def complete_json(self, model: str | None, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        raise LLMError("invalid API key", retryable=False)


async def seed_run(sessions: async_sessionmaker[AsyncSession], run_id: str, order_id: str) -> None:
    async with sessions() as session:
        supervisor = await repo.get_supervisor(session, SUPERVISOR.id)
        if supervisor is None:
            supervisor = await repo.create_supervisor(session, SUPERVISOR, is_template=True)
        await repo.create_run(
            session,
            run_id=run_id,
            order_id=order_id,
            supervisor=supervisor,
            workflow_id=f"wf-{order_id}",
            order_context={"customer": "Asha", "total": 2499},
            instructions=[],
        )
        await session.commit()


async def start(
    env: WorkflowEnvironment,
    sessions: async_sessionmaker[AsyncSession],
    *,
    max_history_events: int = 2000,
) -> WorkflowHandle:
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    order_id = f"ORD-{uuid.uuid4().hex[:6]}"
    await seed_run(sessions, run_id, order_id)
    run = RunInput(
        run_id=run_id,
        order_id=order_id,
        order_context={"customer": "Asha", "total": 2499},
        supervisor=SUPERVISOR,
        max_history_events=max_history_events,
    )
    return await env.client.start_workflow(OrderSupervisorWorkflow.run, run, id=f"wf-{order_id}", task_queue=TASK_QUEUE)


TASK_QUEUE = "test-order-supervisor"


def worker(env: WorkflowEnvironment, sessions: async_sessionmaker[AsyncSession], llm: Any = None) -> Worker:
    activities = SupervisorActivities(llm=llm or MockLLMClient(), sessions=sessions)
    return Worker(env.client, task_queue=TASK_QUEUE, workflows=[OrderSupervisorWorkflow], activities=activities.all())


async def snapshot(handle: WorkflowHandle) -> RunSnapshot:
    return await handle.query(OrderSupervisorWorkflow.snapshot)


async def wait_for(handle: WorkflowHandle, predicate: Callable[[RunSnapshot], bool], seconds: float = 15) -> RunSnapshot:
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        snap = await snapshot(handle)
        if predicate(snap):
            return snap
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"Condition not met; last snapshot: {snap}")
        await asyncio.sleep(0.05)


def event(event_type: str, **payload: Any) -> OrderEvent:
    return OrderEvent(id=uuid.uuid4().hex, type=event_type, payload=payload, occurred_at=datetime.now(UTC), source="test")


def asleep_after(turns: int) -> Callable[[RunSnapshot], bool]:
    return lambda s: s.turn_count == turns and s.status == "sleeping"


async def timeline_titles(sessions: async_sessionmaker[AsyncSession], run_id: str) -> list[tuple[str, str]]:
    async with sessions() as session:
        return [(row.kind, row.title) for row in await repo.list_timeline(session, run_id)]


async def test_full_lifecycle_start_sleep_scheduled_wake_event_and_terminal_close(env, sessions) -> None:
    async with worker(env, sessions):
        handle = await start(env, sessions)
        snap = await wait_for(handle, asleep_after(1))
        run_id = snap.run_id
        assert snap.next_wake_at is not None
        assert snap.memory_summary  # agent wrote memory on its first turn

        # Routine event: recorded, but the agent keeps sleeping.
        await handle.signal(OrderSupervisorWorkflow.ingest_event, event("payment_confirmed"))
        snap = await wait_for(handle, lambda s: s.order_status == "paid")
        assert snap.turn_count == 1
        assert snap.pending_events == 1

        # Scheduled wake-up: skip past the 5 minutes the agent asked for.
        await env.sleep(timedelta(minutes=6))
        await wait_for(handle, asleep_after(2))

        # Critical event wakes the agent immediately.
        await handle.signal(OrderSupervisorWorkflow.ingest_event, event("payment_failed", reason="card_declined"))
        await wait_for(handle, asleep_after(3))

        # Terminal event closes the run with a final report.
        await handle.signal(OrderSupervisorWorkflow.ingest_event, event("delivered"))
        report = await handle.result()

    assert isinstance(report, FinalReport)
    async with sessions() as session:
        row = await repo.get_run(session, run_id)
        executions = await repo.list_tool_executions(session, run_id)
    assert row is not None and row.status == "completed"
    assert row.final_report is not None and row.final_report["summary"]
    assert {e.tool for e in executions} >= {"send_customer_message", "escalate_issue"}
    kinds = {kind for kind, _ in await timeline_titles(sessions, run_id)}
    assert kinds >= {"system", "event", "classification", "wake", "tool", "sleep", "memory"}


async def test_pause_holds_events_until_resume(env, sessions) -> None:
    async with worker(env, sessions):
        handle = await start(env, sessions)
        run_id = (await wait_for(handle, asleep_after(1))).run_id

        await handle.signal(OrderSupervisorWorkflow.pause)
        await wait_for(handle, lambda s: s.status == "paused")
        await handle.signal(OrderSupervisorWorkflow.ingest_event, event("payment_failed"))
        await env.sleep(timedelta(minutes=30))  # scheduled wake-up is also held while paused
        snap = await wait_for(handle, lambda s: s.order_status == "payment_failed")
        assert snap.turn_count == 1
        assert snap.status == "paused"

        await handle.signal(OrderSupervisorWorkflow.resume)
        await wait_for(handle, asleep_after(2))

        await handle.signal(OrderSupervisorWorkflow.terminate, "test over")
        await handle.result()

    async with sessions() as session:
        row = await repo.get_run(session, run_id)
    assert row is not None and row.status == "terminated"
    assert row.close_reason == "test over"
    assert row.final_report is not None


async def test_instruction_and_interrupt_wake_the_agent(env, sessions) -> None:
    async with worker(env, sessions):
        handle = await start(env, sessions)
        await wait_for(handle, asleep_after(1))

        await handle.signal(
            OrderSupervisorWorkflow.add_instruction, InstructionSignal(text="No customer contact", wake_agent=False)
        )
        snap = await wait_for(handle, lambda s: "No customer contact" in s.instructions)
        assert snap.turn_count == 1  # instruction without wake just joins the context

        await handle.signal(OrderSupervisorWorkflow.add_instruction, InstructionSignal(text="Prioritise speed", wake_agent=True))
        await wait_for(handle, asleep_after(2))

        await handle.signal(OrderSupervisorWorkflow.interrupt, "please re-check")
        await wait_for(handle, asleep_after(3))

        await handle.signal(OrderSupervisorWorkflow.terminate, "")
        await handle.result()

    titles = await timeline_titles(sessions, snap.run_id)
    assert ("instruction", "Prioritise speed") in titles
    assert any(kind == "wake" and "manual" in title for kind, title in titles)


async def test_unknown_event_is_escalated(env, sessions) -> None:
    async with worker(env, sessions):
        handle = await start(env, sessions)
        snap = await wait_for(handle, asleep_after(1))
        await handle.signal(OrderSupervisorWorkflow.ingest_event, event("warehouse_fire", building="B2"))
        await wait_for(handle, asleep_after(2))
        await handle.signal(OrderSupervisorWorkflow.terminate, "done")
        await handle.result()

    async with sessions() as session:
        executions = await repo.list_tool_executions(session, snap.run_id)
    assert any(e.tool == "escalate_issue" and "Unrecognised" in e.args["reason"] for e in executions)


async def test_continue_as_new_keeps_state(env, sessions) -> None:
    async with worker(env, sessions):
        handle = await start(env, sessions, max_history_events=40)
        snap = await wait_for(handle, asleep_after(1))
        for _ in range(4):
            await handle.signal(OrderSupervisorWorkflow.ingest_event, event("customer_message_received", message="hi"))
            await asyncio.sleep(0.3)
        await wait_for(handle, lambda s: s.turn_count >= 3 and s.status == "sleeping")
        await handle.signal(OrderSupervisorWorkflow.terminate, "done")
        await handle.result()  # follows the continue-as-new chain

    titles = await timeline_titles(sessions, snap.run_id)
    assert any("Continued as new" in title for _, title in titles)
    async with sessions() as session:
        row = await repo.get_run(session, snap.run_id)
    assert row is not None and row.status == "terminated"
    assert row.turn_count >= 3  # turn counter survived the hand-over


async def test_llm_outage_degrades_gracefully(env, sessions) -> None:
    async with worker(env, sessions, llm=FailingLLM()):
        handle = await start(env, sessions)
        snap = await wait_for(handle, asleep_after(1))
        assert snap.next_wake_at is not None  # fell back to the default wake-up
        await handle.signal(OrderSupervisorWorkflow.terminate, "outage test")
        report = await handle.result()

    assert "LLM was unavailable" in report.learnings[0]
    titles = await timeline_titles(sessions, snap.run_id)
    assert any("Agent step failed" in title for _, title in titles)


async def test_execute_tool_is_idempotent(sessions) -> None:
    run_id, order_id = "run-idem", "ORD-idem"
    await seed_run(sessions, run_id, order_id)
    activities = SupervisorActivities(llm=MockLLMClient(), sessions=sessions)
    request = ExecuteToolInput(
        run_id=run_id,
        order_id=order_id,
        idempotency_key="run-idem:0:1:0:0",
        call=ToolCall(id="c1", name="create_internal_note", args={"note": "hello"}),
    )
    first = await ActivityEnvironment().run(activities.execute_tool, request)
    second = await ActivityEnvironment().run(activities.execute_tool, request)

    assert first.output == second.output
    async with sessions() as session:
        assert len(await repo.list_tool_executions(session, run_id)) == 1


async def test_execute_tool_rejects_invalid_arguments(sessions) -> None:
    activities = SupervisorActivities(llm=MockLLMClient(), sessions=sessions)
    request = ExecuteToolInput(
        run_id="r", order_id="o", idempotency_key="k", call=ToolCall(id="c", name="escalate_issue", args={"team": "x"})
    )
    result = await ActivityEnvironment().run(activities.execute_tool, request)
    assert not result.ok
    assert "Missing" in result.output["error"]


async def test_events_are_kept_when_the_agent_turn_fails(env, sessions) -> None:
    async with worker(env, sessions, llm=FailingLLM()):
        handle = await start(env, sessions)
        await wait_for(handle, asleep_after(1))
        await handle.signal(OrderSupervisorWorkflow.ingest_event, event("payment_failed"))
        snap = await wait_for(handle, asleep_after(2))
        assert snap.pending_events == 1  # still waiting to be shown to the agent
        await handle.signal(OrderSupervisorWorkflow.terminate, "done")
        await handle.result()


async def test_execute_tool_refuses_to_act_while_another_attempt_is_in_flight(sessions) -> None:
    from temporalio.exceptions import ApplicationError

    run_id, order_id = "run-claim", "ORD-claim"
    await seed_run(sessions, run_id, order_id)
    async with sessions() as session:
        await repo.record_tool_execution(
            session,
            idempotency_key="k-claim",
            run_id=run_id,
            order_id=order_id,
            tool="create_internal_note",
            args={},
            result={"status": "pending"},
        )
        await session.commit()
    activities = SupervisorActivities(llm=MockLLMClient(), sessions=sessions)
    request = ExecuteToolInput(
        run_id=run_id,
        order_id=order_id,
        idempotency_key="k-claim",
        call=ToolCall(id="c", name="create_internal_note", args={"note": "x"}),
    )
    with pytest.raises(ApplicationError):
        await ActivityEnvironment().run(activities.execute_tool, request)
