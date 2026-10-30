"""Temporal activities: all I/O for the supervisor (LLM calls, simulated tools, persistence)."""

import secrets

from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.agent import prompts
from app.agent import tools as t
from app.agent.llm import LLMClient, LLMError
from app.db import repository as repo
from app.domain import (
    AgentStepInput,
    AgentStepOutput,
    CompactMemoryInput,
    ExecuteToolInput,
    FinalReport,
    FinalReportInput,
    RunSnapshot,
    TimelineEntry,
    ToolResult,
)

PENDING = "pending"

FINAL_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "outcome": {"type": "string"},
        "key_actions": {"type": "array", "items": {"type": "string"}},
        "learnings": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "outcome", "key_actions", "learnings", "recommendations"],
}


class PersistInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot: RunSnapshot | None = None
    entries: list[TimelineEntry] = []


class CloseRunInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    status: str
    close_reason: str
    final_report: FinalReport | None
    entries: list[TimelineEntry] = []


class SupervisorActivities:
    """Activities are bound to an LLM client and a session factory so tests can inject fakes."""

    def __init__(self, llm: LLMClient, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._llm = llm
        self._sessions = sessions

    @activity.defn
    async def agent_step(self, request: AgentStepInput) -> AgentStepOutput:
        try:
            message = await self._llm.step(request)
        except LLMError as exc:
            raise ApplicationError(str(exc), type="LLMError", non_retryable=not exc.retryable) from exc
        return AgentStepOutput(message=message)

    @activity.defn
    async def execute_tool(self, request: ExecuteToolInput) -> ToolResult:
        call = request.call
        spec = t.ACTION_TOOL_SPECS.get(call.name)
        if spec is None:
            return ToolResult(call_id=call.id, name=call.name, ok=False, output={"error": f"Unknown tool '{call.name}'"})
        error = t.validate_args(spec, call.args)
        if error:
            return ToolResult(call_id=call.id, name=call.name, ok=False, output={"error": error})

        # Claim the idempotency key *before* acting, so concurrent or repeated attempts can't act twice.
        async with self._sessions() as session:
            existing = await repo.get_tool_execution(session, request.idempotency_key)
            if existing is not None:
                if existing.result.get("status") == PENDING:
                    raise ApplicationError("Tool call is still in progress in another attempt", type="ToolInProgress")
                activity.logger.info("Tool call %s already executed; returning stored result", request.idempotency_key)
                return ToolResult(call_id=call.id, name=call.name, ok=True, output=existing.result)
            try:
                await repo.record_tool_execution(
                    session,
                    idempotency_key=request.idempotency_key,
                    run_id=request.run_id,
                    order_id=request.order_id,
                    tool=call.name,
                    args=call.args,
                    result={"status": PENDING},
                )
                await session.commit()
            except IntegrityError as exc:
                raise ApplicationError("Another attempt claimed this tool call", type="ToolInProgress") from exc

        # A real integration would pass `idempotency_key` to the downstream system as well.
        output = _simulate_tool(call.name, call.args)
        async with self._sessions() as session:
            await repo.complete_tool_execution(session, request.idempotency_key, output)
            await session.commit()
        return ToolResult(call_id=call.id, name=call.name, ok=True, output=output)

    @activity.defn
    async def persist(self, request: PersistInput) -> None:
        async with self._sessions() as session:
            if not await self._run_exists(session, request.entries, request.snapshot):
                return
            if request.entries:
                await repo.append_timeline(session, request.entries)
            if request.snapshot is not None:
                await repo.apply_snapshot(session, request.snapshot)
            await session.commit()

    async def _run_exists(self, session: AsyncSession, entries: list[TimelineEntry], snapshot: RunSnapshot | None) -> bool:
        run_id = snapshot.run_id if snapshot else (entries[0].run_id if entries else None)
        if run_id is None or await repo.get_run(session, run_id) is not None:
            return True
        # Retrying can't fix a missing row (e.g. the database was reset); don't block the workflow on it.
        activity.logger.warning("Run %s not found in the database; skipping persistence", run_id)
        return False

    @activity.defn
    async def compact_memory(self, request: CompactMemoryInput) -> str:
        prompt = prompts.build_compaction_prompt(request.memory_summary, request.items)
        try:
            return await self._llm.complete_text(request.model, prompt)
        except LLMError as exc:
            raise ApplicationError(str(exc), type="LLMError", non_retryable=not exc.retryable) from exc

    @activity.defn
    async def generate_final_report(self, request: FinalReportInput) -> FinalReport:
        prompt = prompts.build_final_report_prompt(
            order_id=request.order_id,
            order_context=request.order_context,
            order_status=request.order_status,
            close_reason=request.close_reason,
            memory_summary=request.memory_summary,
            recent=request.recent,
            actions_taken=request.actions_taken,
            instructions=request.instructions,
        )
        try:
            data = await self._llm.complete_json(request.model, prompt, FINAL_REPORT_SCHEMA)
        except LLMError as exc:
            raise ApplicationError(str(exc), type="LLMError", non_retryable=not exc.retryable) from exc
        try:
            return FinalReport.model_validate(data)
        except ValueError as exc:
            raise ApplicationError(f"Final report did not match the schema: {exc}", type="LLMError") from exc

    @activity.defn
    async def close_run(self, request: CloseRunInput) -> None:
        async with self._sessions() as session:
            if await repo.get_run(session, request.run_id) is None:
                activity.logger.warning("Run %s not found in the database; nothing to close", request.run_id)
                return
            if request.entries:
                await repo.append_timeline(session, request.entries)
            await repo.close_run(
                session,
                request.run_id,
                status=request.status,
                close_reason=request.close_reason,
                final_report=request.final_report,
            )
            await session.commit()

    def all(self) -> list:
        return [
            self.agent_step,
            self.execute_tool,
            self.persist,
            self.compact_memory,
            self.generate_final_report,
            self.close_run,
        ]


def _simulate_tool(name: str, args: dict) -> dict:
    """Pretend to call the external system and return what it would have returned."""
    ref = secrets.token_hex(3).upper()
    if name == t.SEND_CUSTOMER_MESSAGE:
        return {"status": "sent", "message_id": f"MSG-{ref}", "channel": args["channel"]}
    if name == t.CREATE_INTERNAL_NOTE:
        return {"status": "created", "note_id": f"NOTE-{ref}"}
    if name == t.ESCALATE_ISSUE:
        return {"status": "opened", "ticket_id": f"ESC-{ref}", "team": args["team"], "severity": args["severity"]}
    if name == t.MARK_ORDER_FOR_REVIEW:
        return {"status": "flagged", "review_id": f"REV-{ref}", "queue": "manual-review"}
    raise ValueError(f"No simulator for tool {name}")
