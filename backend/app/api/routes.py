"""HTTP API for supervisor templates and supervision runs."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import tools as t
from app.api.gateway import WorkflowClosed, WorkflowGateway, WorkflowUnavailable, get_gateway
from app.api.schemas import (
    Accepted,
    EventIn,
    InstructionIn,
    InterruptIn,
    RunCreate,
    RunDetail,
    RunOut,
    SupervisorCreate,
    SupervisorOut,
    TerminateIn,
    TimelineOut,
    ToolExecutionOut,
)
from app.db import repository as repo
from app.db.models import RunRow
from app.db.session import get_sessionmaker
from app.domain import KNOWN_EVENT_TYPES, InstructionSignal, OrderEvent, RunInput, SupervisorConfig, WakeAggressiveness
from app.temporal_client import workflow_id_for_order

router = APIRouter(prefix="/api")


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
GatewayDep = Annotated[WorkflowGateway, Depends(get_gateway)]


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# --- Metadata -----------------------------------------------------------------------------------


@router.get("/meta")
async def meta() -> dict[str, Any]:
    """Options the UI needs to render forms (tools, event types, aggressiveness levels)."""
    return {
        "action_tools": [spec.model_dump() for spec in t.ACTION_TOOL_SPECS.values()],
        "control_tools": [spec.model_dump() for spec in t.CONTROL_TOOL_SPECS.values()],
        "event_types": sorted(KNOWN_EVENT_TYPES),
        "wake_aggressiveness": [level.value for level in WakeAggressiveness],
    }


# --- Supervisors --------------------------------------------------------------------------------


@router.get("/supervisors", response_model=list[SupervisorOut])
async def list_supervisors(session: SessionDep) -> list[Any]:
    return list(await repo.list_supervisors(session))


@router.get("/supervisors/{supervisor_id}", response_model=SupervisorOut)
async def get_supervisor(supervisor_id: str, session: SessionDep) -> Any:
    row = await repo.get_supervisor(session, supervisor_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supervisor not found")
    return row


@router.post("/supervisors", response_model=SupervisorOut, status_code=status.HTTP_201_CREATED)
async def create_supervisor(body: SupervisorCreate, session: SessionDep) -> Any:
    if body.max_sleep_minutes < body.default_wake_minutes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "max_sleep_minutes must be >= default_wake_minutes")
    config = SupervisorConfig(id=_new_id("sup"), **body.model_dump())
    row = await repo.create_supervisor(session, config)
    await session.commit()
    return row


# --- Runs ---------------------------------------------------------------------------------------


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def start_run(body: RunCreate, session: SessionDep, gateway: GatewayDep) -> Any:
    supervisor = await repo.get_supervisor(session, body.supervisor_id)
    if supervisor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supervisor not found")
    await _release_stale_run(session, gateway, body.order_id)

    instructions = [i.strip() for i in body.instructions if i.strip()]
    run_id = _new_id("run")
    workflow_id = workflow_id_for_order(body.order_id)
    try:
        row = await repo.create_run(
            session,
            run_id=run_id,
            order_id=body.order_id,
            supervisor=supervisor,
            workflow_id=workflow_id,
            order_context=body.order_context,
            instructions=instructions,
        )
        await session.commit()
    except IntegrityError as exc:  # another request opened a run for this order at the same moment
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Order {body.order_id} already has an active supervisor run") from exc

    run_input = RunInput(
        run_id=run_id,
        order_id=body.order_id,
        order_context=body.order_context,
        supervisor=repo.supervisor_to_config(supervisor),
        instructions=instructions,
    )
    try:
        await gateway.start(workflow_id, run_input)
    except (WorkflowUnavailable, WorkflowClosed) as exc:
        await repo.close_run(session, run_id, status="failed", close_reason=str(exc), final_report=None)
        await session.commit()
        code = status.HTTP_409_CONFLICT if isinstance(exc, WorkflowClosed) else status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(code, str(exc)) from exc
    await session.refresh(row)
    return row


async def _release_stale_run(session: AsyncSession, gateway: WorkflowGateway, order_id: str) -> None:
    """409 if the order already has a live run; if the DB says open but the workflow is gone, mark it failed."""
    existing = await repo.find_open_run_for_order(session, order_id)
    if existing is None:
        return
    try:
        running = await gateway.is_running(existing.workflow_id)
    except WorkflowUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Order {order_id} already has an active supervisor run")
    await repo.close_run(
        session, existing.id, status="failed", close_reason="Workflow stopped outside the app", final_report=None
    )
    await session.commit()


@router.get("/runs", response_model=list[RunOut])
async def list_runs(session: SessionDep, active: Annotated[bool | None, Query()] = None) -> list[Any]:
    return list(await repo.list_runs(session, active=active))


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, session: SessionDep) -> RunDetail:
    row = await _require_run(session, run_id)
    timeline = await repo.list_timeline(session, run_id)
    executions = await repo.list_tool_executions(session, run_id)
    return RunDetail(
        **RunOut.model_validate(row).model_dump(),
        timeline=[TimelineOut.model_validate(e) for e in timeline],
        tool_executions=[ToolExecutionOut.model_validate(e) for e in executions],
    )


@router.post("/runs/{run_id}/events", response_model=Accepted, status_code=status.HTTP_202_ACCEPTED)
async def send_event(run_id: str, body: EventIn, session: SessionDep, gateway: GatewayDep) -> Accepted:
    row = await _require_open_run(session, run_id)
    event = OrderEvent(id=_new_id("evt"), type=body.type, payload=body.payload, occurred_at=datetime.now(UTC), source=body.source)
    await _signal(gateway, row, "ingest_event", event)
    return Accepted(message=f"Event '{body.type}' delivered to the workflow")


@router.post("/runs/{run_id}/instructions", response_model=Accepted, status_code=status.HTTP_202_ACCEPTED)
async def add_instruction(run_id: str, body: InstructionIn, session: SessionDep, gateway: GatewayDep) -> Accepted:
    row = await _require_open_run(session, run_id)
    await _signal(gateway, row, "add_instruction", InstructionSignal(text=body.text, wake_agent=body.wake_agent))
    return Accepted(message="Instruction added to the run")


@router.post("/runs/{run_id}/interrupt", response_model=Accepted, status_code=status.HTTP_202_ACCEPTED)
async def interrupt_run(run_id: str, body: InterruptIn, session: SessionDep, gateway: GatewayDep) -> Accepted:
    row = await _require_open_run(session, run_id)
    await _signal(gateway, row, "interrupt", body.note.strip())
    return Accepted(message="Agent will wake up for an immediate review")


@router.post("/runs/{run_id}/pause", response_model=Accepted, status_code=status.HTTP_202_ACCEPTED)
async def pause_run(run_id: str, session: SessionDep, gateway: GatewayDep) -> Accepted:
    row = await _require_open_run(session, run_id)
    await _signal(gateway, row, "pause")
    return Accepted(message="Run paused")


@router.post("/runs/{run_id}/resume", response_model=Accepted, status_code=status.HTTP_202_ACCEPTED)
async def resume_run(run_id: str, session: SessionDep, gateway: GatewayDep) -> Accepted:
    row = await _require_open_run(session, run_id)
    await _signal(gateway, row, "resume")
    return Accepted(message="Run resumed")


@router.post("/runs/{run_id}/terminate", response_model=Accepted, status_code=status.HTTP_202_ACCEPTED)
async def terminate_run(run_id: str, body: TerminateIn, session: SessionDep, gateway: GatewayDep) -> Accepted:
    row = await _require_open_run(session, run_id)
    await _signal(gateway, row, "terminate", body.reason.strip() or "Terminated by operator")
    return Accepted(message="Run will write its final report and close")


# --- Helpers ------------------------------------------------------------------------------------


async def _require_run(session: AsyncSession, run_id: str) -> RunRow:
    row = await repo.get_run(session, run_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return row


async def _require_open_run(session: AsyncSession, run_id: str) -> RunRow:
    row = await _require_run(session, run_id)
    if row.status in repo.TERMINAL_RUN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Run is already {row.status}")
    return row


async def _signal(gateway: WorkflowGateway, row: RunRow, name: str, arg: Any | None = None) -> None:
    try:
        await gateway.signal(row.workflow_id, name, arg)
    except WorkflowClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except WorkflowUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
