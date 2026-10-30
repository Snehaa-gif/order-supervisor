"""The long-running Temporal workflow: one run supervises one order until it is closed.

Lifecycle
---------
start -> agent turn (trigger: workflow_start) -> sleep
      -> wakes on: an important event signal | its scheduled wake-up time | a human interrupt
      -> agent turn -> sleep -> ... -> close (agent decision, terminal order state, or terminate signal)
      -> final report (summary, actions, learnings, recommendations)

The workflow only holds orchestration state and makes deterministic decisions.
Every side effect (LLM calls, simulated tools, database writes) happens in an activity.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from app.agent import tools as t
    from app.agent.classifier import classify_event
    from app.agent.prompts import build_system_prompt, build_turn_prompt
    from app.domain import (
        EVENT_TO_ORDER_STATUS,
        TERMINAL_EVENT_TYPES,
        AgentStepInput,
        CarriedState,
        ChatMessage,
        CompactMemoryInput,
        ExecuteToolInput,
        FinalReport,
        FinalReportInput,
        InstructionSignal,
        MemoryItem,
        OrderEvent,
        PendingWake,
        RunInput,
        RunSnapshot,
        RunStatus,
        TimelineEntry,
        TimelineKind,
        ToolCall,
        ToolResult,
        WakeGuidance,
        WakeTrigger,
    )
    from app.workflows.activities import CloseRunInput, PersistInput, SupervisorActivities

MAX_STEPS_PER_TURN = 6  # model calls per wake-up; bounds cost and runaway loops
# Long enough for the Gemini adapter to try every fallback model (20s request timeout each).
LLM_ACTIVITY_TIMEOUT = timedelta(seconds=150)
RECENT_MEMORY_LIMIT = 16  # important items kept verbatim before compaction kicks in
RECENT_MEMORY_KEEP = 6  # items kept verbatim after compaction
MAX_UNSEEN_EVENTS = 25
MEMORY_MAX_CHARS = 1500

WAKE_PRIORITY: dict[WakeTrigger, int] = {"scheduled": 1, "event": 2, "manual": 3, "terminal": 4, "workflow_start": 5}

LLM_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=3),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=40),
    maximum_attempts=6,
    non_retryable_error_types=["ValidationError"],
)
TOOL_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=5)
DB_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=30))


@workflow.defn
class OrderSupervisorWorkflow:
    @workflow.init
    def __init__(self, run: RunInput) -> None:
        self._run = run
        self._supervisor = run.supervisor
        carried = run.carried_state
        self._order_status = carried.order_status if carried else "created"
        self._memory_summary = carried.memory_summary if carried else ""
        self._recent: list[MemoryItem] = list(carried.recent) if carried else []
        self._unseen_events: list[OrderEvent] = list(carried.unseen_events) if carried else []
        self._inbox: list[OrderEvent] = list(carried.inbox) if carried else []
        self._wake_guidance = carried.wake_guidance if carried else WakeGuidance()
        self._instructions: list[str] = list(carried.instructions) if carried else list(run.instructions)
        self._next_wake_at = carried.next_wake_at if carried else None
        self._paused = carried.paused if carried else False
        self._turn_count = carried.turn_count if carried else 0
        self._actions_taken: list[str] = list(carried.actions_taken) if carried else []
        self._generation = carried.generation if carried else 0
        self._pending_wake: PendingWake | None = carried.pending_wake if carried else None

        self._status: RunStatus = "starting" if not carried else ("paused" if self._paused else "sleeping")
        self._close_reason: str | None = None
        self._terminate_reason: str | None = None
        self._control_version = 0  # bumped by pause/resume so the sleep loop re-evaluates
        self._scheduled_this_turn = False
        self._pending_entries: list[TimelineEntry] = []

    # --- Entry point ----------------------------------------------------------------------------

    @workflow.run
    async def run(self, run: RunInput) -> FinalReport:
        if run.carried_state is None:
            self._log("system", f"Supervisor '{self._supervisor.name}' started for order {run.order_id}", important=True)
            self._remember(f"Supervision started. Order context: {run.order_context}")
            await self._agent_turn("workflow_start", "")
        else:
            self._log("system", f"Continued as new (generation {self._generation}) to keep history small")

        while self._close_reason is None and self._terminate_reason is None:
            await self._flush()
            self._maybe_continue_as_new()
            await self._sleep()
            self._drain_inbox()
            self._check_schedule()
            if self._terminate_reason is not None or self._paused or self._pending_wake is None:
                continue
            wake, self._pending_wake = self._pending_wake, None
            await self._agent_turn(wake.trigger, wake.note)
            if wake.trigger == "terminal" and self._close_reason is None:
                self._close_reason = f"Order reached a terminal state ({self._order_status})."
                self._log("system", "Auto-closing: order is in a terminal state", important=True)

        return await self._finish()

    # --- Signals / queries ----------------------------------------------------------------------

    @workflow.signal
    def ingest_event(self, event: OrderEvent) -> None:
        self._inbox.append(event)

    @workflow.signal
    def add_instruction(self, signal: InstructionSignal) -> None:
        self._instructions.append(signal.text)
        self._remember(f"Human instruction added: {signal.text}")
        self._log("instruction", signal.text, {"wake_agent": signal.wake_agent}, important=True)
        if signal.wake_agent:
            self._request_wake("manual", f"New instruction: {signal.text}")

    @workflow.signal
    def pause(self) -> None:
        if self._paused:
            return
        self._paused = True
        self._control_version += 1
        self._log("control", "Run paused by operator: agent will not act until resumed", important=True)

    @workflow.signal
    def resume(self) -> None:
        if not self._paused:
            return
        self._paused = False
        self._control_version += 1
        self._log("control", "Run resumed by operator", important=True)

    @workflow.signal
    def interrupt(self, note: str) -> None:
        self._log("control", "Operator interrupted sleep for an immediate review", {"note": note}, important=True)
        self._request_wake("manual", note)

    @workflow.signal
    def terminate(self, reason: str) -> None:
        if self._terminate_reason is None:
            self._terminate_reason = reason or "Terminated by operator"
            self._log("control", f"Terminate requested: {self._terminate_reason}", important=True)

    @workflow.query
    def snapshot(self) -> RunSnapshot:
        return RunSnapshot(
            run_id=self._run.run_id,
            status=self._status,
            order_status=self._order_status,
            memory_summary=self._memory_summary,
            next_wake_at=self._next_wake_at,
            wake_guidance=self._wake_guidance,
            instructions=list(self._instructions),
            turn_count=self._turn_count,
            pending_events=len(self._inbox) + len(self._unseen_events),
        )

    # --- Sleeping and waking --------------------------------------------------------------------

    async def _sleep(self) -> None:
        """Block until a signal arrives, the scheduled wake-up is due, or a control changes."""
        if self._has_work():
            return
        self._status = "paused" if self._paused else "sleeping"
        await self._flush()

        version = self._control_version
        timeout = None if self._paused else self._seconds_until_wake()
        if timeout is not None and timeout <= 0:
            return
        try:
            await workflow.wait_condition(
                lambda: self._has_work() or self._control_version != version,
                timeout=timeout,
            )
        except TimeoutError:
            pass  # scheduled wake-up time reached; _check_schedule() handles it

    def _has_work(self) -> bool:
        return bool(self._inbox) or self._terminate_reason is not None or (not self._paused and self._pending_wake is not None)

    def _seconds_until_wake(self) -> float | None:
        if self._next_wake_at is None:
            return None
        return (self._next_wake_at - workflow.now()).total_seconds()

    def _check_schedule(self) -> None:
        if self._paused or self._next_wake_at is None or workflow.now() < self._next_wake_at:
            return
        self._next_wake_at = None
        self._request_wake("scheduled", "")

    def _request_wake(self, trigger: WakeTrigger, note: str) -> None:
        current = self._pending_wake
        if current is None:
            self._pending_wake = PendingWake(trigger=trigger, note=note)
            return
        winner = trigger if WAKE_PRIORITY[trigger] > WAKE_PRIORITY[current.trigger] else current.trigger
        notes = "; ".join(n for n in (current.note, note) if n)
        self._pending_wake = PendingWake(trigger=winner, note=notes)

    def _drain_inbox(self) -> None:
        while self._inbox:
            self._handle_event(self._inbox.pop(0))

    def _handle_event(self, event: OrderEvent) -> None:
        self._order_status = EVENT_TO_ORDER_STATUS.get(event.type, self._order_status)
        self._log("event", event.type, {"payload": event.payload, "source": event.source, "event_id": event.id}, important=True)
        self._remember(f"Event {event.type} {event.payload or ''}".strip())
        self._unseen_events = [*self._unseen_events, event][-MAX_UNSEEN_EVENTS:]

        result = classify_event(event, self._supervisor.wake_aggressiveness, self._wake_guidance)
        verdict = "Wake agent now" if result.wakes else "Let agent sleep"
        self._log("classification", f"{verdict}: {event.type}", {"reason": result.reason, "unknown_event": result.unknown_event})
        if event.type in TERMINAL_EVENT_TYPES:
            self._request_wake("terminal", f"{event.type}: {result.reason}")
        elif result.wakes:
            self._request_wake("event", f"{event.type}: {result.reason}")
        if self._paused and result.wakes:
            self._log("control", "Run is paused: the agent will review this after resume")

    # --- Agent turn -----------------------------------------------------------------------------

    async def _agent_turn(self, trigger: WakeTrigger, note: str) -> None:
        self._status = "awake"
        self._turn_count += 1
        self._scheduled_this_turn = False
        self._next_wake_at = None
        new_events, self._unseen_events = self._unseen_events, []
        self._log(
            "wake", f"Agent woke up ({trigger.replace('_', ' ')})", {"note": note, "turn": self._turn_count}, important=True
        )
        await self._flush()

        messages = [ChatMessage(role="user", text=self._turn_prompt(trigger, note, new_events))]
        for step in range(MAX_STEPS_PER_TURN):
            reply = await self._model_step(messages)
            if reply is None:
                if step == 0:
                    # The agent never saw these events; keep them for the next attempt.
                    self._unseen_events = [*new_events, *self._unseen_events][-MAX_UNSEEN_EVENTS:]
                break
            messages.append(reply)
            if reply.text:
                self._log("agent", reply.text, {"turn": self._turn_count, "step": step})
            if not reply.tool_calls:
                break
            results = await self._run_tools(reply.tool_calls, step)
            messages.append(ChatMessage(role="tool", tool_results=results))
            if self._close_reason is not None or self._terminate_reason is not None:
                break
            # The sleep decision ends the turn, saving a model call - unless a tool failed and
            # the agent should get the chance to react to the error.
            if self._scheduled_this_turn and all(r.ok for r in results):
                break

        if self._close_reason is None and not self._scheduled_this_turn:
            minutes = self._supervisor.default_wake_minutes
            self._next_wake_at = workflow.now() + timedelta(minutes=minutes)
            self._log(
                "sleep", f"No wake-up chosen; defaulting to {minutes} min", {"next_wake_at": self._next_wake_at.isoformat()}
            )
        await self._maybe_compact()

    def _turn_prompt(self, trigger: WakeTrigger, note: str, new_events: list[OrderEvent]) -> str:
        return build_turn_prompt(
            trigger=trigger,
            trigger_note=note,
            now=workflow.now(),
            order_id=self._run.order_id,
            order_status=self._order_status,
            order_context=self._run.order_context,
            memory_summary=self._memory_summary,
            recent=self._recent,
            new_events=new_events,
            actions_taken=self._actions_taken,
            wake_guidance=self._wake_guidance,
        )

    async def _model_step(self, messages: list[ChatMessage]) -> ChatMessage | None:
        request = AgentStepInput(
            model=self._supervisor.model,
            system_prompt=build_system_prompt(self._supervisor, self._instructions),
            messages=messages,
            tools=t.tool_specs_for(self._supervisor.tools),
        )
        try:
            output = await workflow.execute_activity_method(
                SupervisorActivities.agent_step,
                request,
                start_to_close_timeout=LLM_ACTIVITY_TIMEOUT,
                retry_policy=LLM_RETRY,
            )
        except ActivityError as exc:
            self._log("system", "Agent step failed; will retry at next wake-up", {"error": _error_text(exc)}, important=True)
            return None
        return output.message

    # --- Tools ----------------------------------------------------------------------------------

    async def _run_tools(self, calls: list[ToolCall], step: int) -> list[ToolResult]:
        results: list[ToolResult] = []
        for index, call in enumerate(calls):
            if self._close_reason is not None:
                break  # the agent closed the run; ignore anything it queued after that
            results.append(await self._run_tool(call, f"{step}:{index}"))
        return results

    async def _run_tool(self, call: ToolCall, position: str) -> ToolResult:
        if t.is_control_tool(call.name):
            result = self._run_control_tool(call)
        elif call.name in self._supervisor.tools:
            result = await self._run_action_tool(call, position)
        else:
            result = _failed(call, f"Tool '{call.name}' is not enabled for this supervisor.")
        # Successful control tools already log their own, more specific timeline entry.
        if not (result.ok and t.is_control_tool(call.name)):
            self._log("tool", call.name, {"args": call.args, "ok": result.ok, "output": result.output}, important=result.ok)
        return result

    async def _run_action_tool(self, call: ToolCall, position: str) -> ToolResult:
        request = ExecuteToolInput(
            run_id=self._run.run_id,
            order_id=self._run.order_id,
            idempotency_key=f"{self._run.run_id}:{self._generation}:{self._turn_count}:{position}",
            call=call,
        )
        try:
            result = await workflow.execute_activity_method(
                SupervisorActivities.execute_tool,
                request,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=TOOL_RETRY,
            )
        except ActivityError as exc:
            return _failed(call, f"Tool execution failed: {_error_text(exc)}")
        if result.ok:
            summary = _describe_action(call)
            self._actions_taken = [*self._actions_taken, summary]
            self._remember(f"Action: {summary}")
        return result

    def _run_control_tool(self, call: ToolCall) -> ToolResult:
        error = t.validate_args(t.CONTROL_TOOL_SPECS[call.name], call.args)
        if error:
            return _failed(call, error)
        args = call.args
        if call.name == t.SCHEDULE_NEXT_WAKE:
            return self._schedule_wake(call)
        if call.name == t.UPDATE_MEMORY:
            self._memory_summary = str(args["summary"])[:MEMORY_MAX_CHARS]
            self._log("memory", "Agent updated its memory", {"summary": self._memory_summary})
            return _ok(call, {"saved": True})
        if call.name == t.SET_WAKE_GUIDANCE:
            self._wake_guidance = WakeGuidance(
                wake_on=[str(x) for x in args.get("wake_on") or []],
                ignore=[str(x) for x in args.get("ignore") or []],
                note=str(args.get("note", "")),
            )
            self._log("memory", "Agent updated its wake-up guidance", self._wake_guidance.model_dump())
            return _ok(call, {"saved": True})
        self._close_reason = str(args["reason"])
        self._log("system", f"Agent closed the run: {self._close_reason}", important=True)
        return _ok(call, {"closing": True})

    def _schedule_wake(self, call: ToolCall) -> ToolResult:
        try:
            requested = int(call.args["minutes"])
        except (TypeError, ValueError):
            return _failed(call, "'minutes' must be an integer")
        minutes = max(1, min(requested, self._supervisor.max_sleep_minutes))
        self._next_wake_at = workflow.now() + timedelta(minutes=minutes)
        self._scheduled_this_turn = True
        reason = str(call.args.get("reason", ""))
        self._log(
            "sleep",
            f"Agent will sleep for {minutes} min",
            {"reason": reason, "next_wake_at": self._next_wake_at.isoformat(), "requested_minutes": requested},
        )
        return _ok(call, {"next_wake_at": self._next_wake_at.isoformat(), "minutes": minutes})

    # --- Memory ---------------------------------------------------------------------------------

    def _remember(self, text: str) -> None:
        self._recent = [*self._recent, MemoryItem(at=workflow.now(), text=text[:500])]

    async def _maybe_compact(self) -> None:
        if len(self._recent) <= RECENT_MEMORY_LIMIT:
            return
        older, keep = self._recent[:-RECENT_MEMORY_KEEP], self._recent[-RECENT_MEMORY_KEEP:]
        try:
            summary = await workflow.execute_activity_method(
                SupervisorActivities.compact_memory,
                CompactMemoryInput(model=self._supervisor.model, memory_summary=self._memory_summary, items=older),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=LLM_RETRY,
            )
        except ActivityError as exc:
            # Fallback: keep a terse trail instead of losing the history entirely.
            summary = (self._memory_summary + " | Earlier: " + "; ".join(i.text for i in older[-5:]))[-MEMORY_MAX_CHARS:]
            self._log("system", "Memory compaction via LLM failed; used a plain-text fallback", {"error": _error_text(exc)})
        self._memory_summary = summary[:MEMORY_MAX_CHARS]
        self._recent = keep
        self._log(
            "memory", f"Compacted {len(older)} older history items into the memory summary", {"summary": self._memory_summary}
        )

    # --- Persistence, history size and shutdown -------------------------------------------------

    def _log(self, kind: TimelineKind, title: str, detail: dict | None = None, *, important: bool = False) -> None:
        self._pending_entries.append(
            TimelineEntry(
                run_id=self._run.run_id, at=workflow.now(), kind=kind, title=title, detail=detail or {}, important=important
            )
        )

    async def _flush(self) -> None:
        entries, self._pending_entries = self._pending_entries, []
        await workflow.execute_activity_method(
            SupervisorActivities.persist,
            PersistInput(snapshot=self.snapshot(), entries=entries),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DB_RETRY,
        )

    def _maybe_continue_as_new(self) -> None:
        info = workflow.info()
        too_long = info.get_current_history_length() >= self._run.max_history_events
        if not (too_long or info.is_continue_as_new_suggested()):
            return
        if self._inbox or self._pending_entries or not workflow.all_handlers_finished():
            return  # never drop a signal: only hand over when fully idle
        carried = CarriedState(
            order_status=self._order_status,
            memory_summary=self._memory_summary,
            recent=self._recent,
            unseen_events=self._unseen_events,
            wake_guidance=self._wake_guidance,
            instructions=self._instructions,
            next_wake_at=self._next_wake_at,
            paused=self._paused,
            turn_count=self._turn_count,
            actions_taken=self._actions_taken,
            generation=self._generation + 1,
            inbox=self._inbox,
            pending_wake=self._pending_wake,
        )
        workflow.continue_as_new(self._run.model_copy(update={"carried_state": carried, "instructions": self._instructions}))

    async def _finish(self) -> FinalReport:
        terminated = self._terminate_reason is not None
        reason = self._terminate_reason if terminated else (self._close_reason or "Closed")
        self._status = "completing"
        self._next_wake_at = None
        self._log("system", "Writing the end-of-run report")
        await self._flush()

        report = await self._final_report(reason)
        entries = [
            TimelineEntry(
                run_id=self._run.run_id,
                at=workflow.now(),
                kind="system",
                title=f"Run {'terminated' if terminated else 'completed'}: {reason}",
                detail={"report": report.model_dump()},
                important=True,
            )
        ]
        await workflow.execute_activity_method(
            SupervisorActivities.close_run,
            CloseRunInput(
                run_id=self._run.run_id,
                status="terminated" if terminated else "completed",
                close_reason=reason,
                final_report=report,
                entries=entries,
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DB_RETRY,
        )
        self._status = "terminated" if terminated else "completed"
        return report

    async def _final_report(self, reason: str) -> FinalReport:
        request = FinalReportInput(
            run_id=self._run.run_id,
            model=self._supervisor.model,
            order_id=self._run.order_id,
            order_context=self._run.order_context,
            order_status=self._order_status,
            close_reason=reason,
            memory_summary=self._memory_summary,
            recent=self._recent,
            actions_taken=self._actions_taken,
            instructions=self._instructions,
        )
        try:
            return await workflow.execute_activity_method(
                SupervisorActivities.generate_final_report,
                request,
                start_to_close_timeout=LLM_ACTIVITY_TIMEOUT,
                retry_policy=LLM_RETRY,
            )
        except ActivityError as exc:
            self._log("system", "LLM final report failed; produced a basic report instead", {"error": _error_text(exc)})
            return FinalReport(
                summary=f"Run ended ({reason}). Order status: {self._order_status}. {self._memory_summary}".strip(),
                outcome=self._order_status,
                key_actions=self._actions_taken or ["No actions taken"],
                learnings=["The LLM was unavailable when the run closed, so no learnings were generated."],
                recommendations=["Check the LLM provider configuration and quota."],
            )


# --- Helpers ------------------------------------------------------------------------------------


def _ok(call: ToolCall, output: dict) -> ToolResult:
    return ToolResult(call_id=call.id, name=call.name, ok=True, output=output)


def _failed(call: ToolCall, error: str) -> ToolResult:
    return ToolResult(call_id=call.id, name=call.name, ok=False, output={"error": error})


def _describe_action(call: ToolCall) -> str:
    args = call.args
    if call.name == t.SEND_CUSTOMER_MESSAGE:
        return f'Messaged customer via {args.get("channel")}: "{str(args.get("message", ""))[:160]}"'
    if call.name == t.ESCALATE_ISSUE:
        return f"Escalated to {args.get('team')} ({args.get('severity')}): {args.get('reason')}"
    if call.name == t.MARK_ORDER_FOR_REVIEW:
        return f"Marked order for review: {args.get('reason')}"
    if call.name == t.CREATE_INTERNAL_NOTE:
        return f"Internal note: {args.get('note')}"
    return f"{call.name}: {args}"


def _error_text(exc: BaseException) -> str:
    cause = exc.cause if isinstance(exc, ActivityError) and exc.cause else exc
    return str(cause)[:300]
