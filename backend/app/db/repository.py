"""Data access for supervisors, runs, timeline entries and simulated tool side effects."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RunRow, SupervisorRow, TimelineRow, ToolExecutionRow, utcnow
from app.domain import FinalReport, RunSnapshot, SupervisorConfig, TimelineEntry, WakeAggressiveness

TERMINAL_RUN_STATUSES = frozenset({"completed", "terminated", "failed"})


# --- Supervisors --------------------------------------------------------------------------------


def supervisor_to_config(row: SupervisorRow) -> SupervisorConfig:
    return SupervisorConfig(
        id=row.id,
        name=row.name,
        base_instruction=row.base_instruction,
        tools=list(row.tools),
        default_wake_minutes=row.default_wake_minutes,
        max_sleep_minutes=row.max_sleep_minutes,
        wake_aggressiveness=WakeAggressiveness(row.wake_aggressiveness),
        model=row.model,
    )


async def list_supervisors(session: AsyncSession) -> Sequence[SupervisorRow]:
    result = await session.scalars(select(SupervisorRow).order_by(SupervisorRow.is_template.desc(), SupervisorRow.created_at))
    return result.all()


async def get_supervisor(session: AsyncSession, supervisor_id: str) -> SupervisorRow | None:
    return await session.get(SupervisorRow, supervisor_id)


async def create_supervisor(session: AsyncSession, config: SupervisorConfig, *, is_template: bool = False) -> SupervisorRow:
    row = SupervisorRow(
        id=config.id,
        name=config.name,
        base_instruction=config.base_instruction,
        tools=list(config.tools),
        default_wake_minutes=config.default_wake_minutes,
        max_sleep_minutes=config.max_sleep_minutes,
        wake_aggressiveness=config.wake_aggressiveness.value,
        model=config.model,
        is_template=is_template,
    )
    session.add(row)
    await session.flush()
    return row


# --- Runs ---------------------------------------------------------------------------------------


async def create_run(
    session: AsyncSession,
    *,
    run_id: str,
    order_id: str,
    supervisor: SupervisorRow,
    workflow_id: str,
    order_context: dict[str, Any],
    instructions: list[str],
) -> RunRow:
    row = RunRow(
        id=run_id,
        order_id=order_id,
        supervisor_id=supervisor.id,
        supervisor_name=supervisor.name,
        workflow_id=workflow_id,
        status="starting",
        order_status="created",
        order_context=order_context,
        instructions=instructions,
        wake_guidance={},
    )
    session.add(row)
    await session.flush()
    return row


async def get_run(session: AsyncSession, run_id: str) -> RunRow | None:
    return await session.get(RunRow, run_id)


async def find_open_run_for_order(session: AsyncSession, order_id: str) -> RunRow | None:
    result = await session.scalars(select(RunRow).where(RunRow.order_id == order_id, RunRow.status.not_in(TERMINAL_RUN_STATUSES)))
    return result.first()


async def list_runs(session: AsyncSession, *, active: bool | None = None) -> Sequence[RunRow]:
    query = select(RunRow).order_by(RunRow.created_at.desc())
    if active is True:
        query = query.where(RunRow.status.not_in(TERMINAL_RUN_STATUSES))
    elif active is False:
        query = query.where(RunRow.status.in_(TERMINAL_RUN_STATUSES))
    result = await session.scalars(query)
    return result.all()


async def apply_snapshot(session: AsyncSession, snapshot: RunSnapshot) -> None:
    row = await session.get(RunRow, snapshot.run_id)
    if row is None:
        raise LookupError(f"Run {snapshot.run_id} not found")
    if row.status in TERMINAL_RUN_STATUSES:
        return  # never resurrect a closed run from a late write
    row.status = snapshot.status
    row.order_status = snapshot.order_status
    row.memory_summary = snapshot.memory_summary
    row.next_wake_at = snapshot.next_wake_at
    row.wake_guidance = snapshot.wake_guidance.model_dump()
    row.instructions = list(snapshot.instructions)
    row.turn_count = snapshot.turn_count
    row.pending_events = snapshot.pending_events


async def close_run(
    session: AsyncSession,
    run_id: str,
    *,
    status: str,
    close_reason: str,
    final_report: FinalReport | None,
    closed_at: datetime | None = None,
) -> None:
    row = await session.get(RunRow, run_id)
    if row is None:
        raise LookupError(f"Run {run_id} not found")
    row.status = status
    row.close_reason = close_reason
    row.final_report = final_report.model_dump() if final_report else None
    row.next_wake_at = None
    row.pending_events = 0
    row.closed_at = closed_at or utcnow()


# --- Timeline -----------------------------------------------------------------------------------


async def append_timeline(session: AsyncSession, entries: Sequence[TimelineEntry]) -> None:
    session.add_all(
        TimelineRow(run_id=e.run_id, at=e.at, kind=e.kind, title=e.title, detail=e.detail, important=e.important) for e in entries
    )


async def list_timeline(session: AsyncSession, run_id: str) -> Sequence[TimelineRow]:
    result = await session.scalars(
        select(TimelineRow).where(TimelineRow.run_id == run_id).order_by(TimelineRow.at, TimelineRow.id)
    )
    return result.all()


# --- Tool executions ----------------------------------------------------------------------------


async def get_tool_execution(session: AsyncSession, idempotency_key: str) -> ToolExecutionRow | None:
    return await session.get(ToolExecutionRow, idempotency_key)


async def record_tool_execution(
    session: AsyncSession,
    *,
    idempotency_key: str,
    run_id: str,
    order_id: str,
    tool: str,
    args: dict[str, Any],
    result: dict[str, Any],
) -> None:
    session.add(
        ToolExecutionRow(idempotency_key=idempotency_key, run_id=run_id, order_id=order_id, tool=tool, args=args, result=result)
    )


async def complete_tool_execution(session: AsyncSession, idempotency_key: str, result: dict[str, Any]) -> None:
    row = await session.get(ToolExecutionRow, idempotency_key)
    if row is None:
        raise LookupError(f"Tool execution {idempotency_key} not found")
    row.result = result


async def list_tool_executions(session: AsyncSession, run_id: str) -> Sequence[ToolExecutionRow]:
    result = await session.scalars(
        select(ToolExecutionRow).where(ToolExecutionRow.run_id == run_id).order_by(ToolExecutionRow.created_at)
    )
    return result.all()
