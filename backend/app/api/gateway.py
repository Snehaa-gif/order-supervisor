"""Thin boundary between the HTTP API and Temporal, so the API can be tested without a server."""

from typing import Any, Protocol

from temporalio.client import Client, WorkflowExecutionStatus, WorkflowHandle
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from app.config import get_settings
from app.domain import RunInput
from app.temporal_client import get_temporal_client
from app.workflows.order_supervisor import OrderSupervisorWorkflow


class WorkflowUnavailable(Exception):
    """Temporal could not be reached or failed to answer (maps to HTTP 503)."""


class WorkflowClosed(Exception):
    """The workflow does not exist, is already running, or is no longer running (maps to HTTP 409)."""


class WorkflowGateway(Protocol):
    async def start(self, workflow_id: str, run: RunInput) -> None: ...

    async def signal(self, workflow_id: str, name: str, arg: Any | None = None) -> None: ...

    async def is_running(self, workflow_id: str) -> bool: ...


async def _client() -> Client:
    try:
        return await get_temporal_client()
    except RuntimeError as exc:  # raised by Client.connect when the server is unreachable
        raise WorkflowUnavailable(f"Temporal is not reachable: {exc}") from exc


def _translate(exc: RPCError, action: str) -> Exception:
    if exc.status == RPCStatusCode.NOT_FOUND:
        return WorkflowClosed(f"Workflow is not running ({action}): {exc.message}")
    return WorkflowUnavailable(f"Temporal error while trying to {action}: {exc.message}")


class TemporalGateway:
    async def start(self, workflow_id: str, run: RunInput) -> None:
        client = await _client()
        try:
            await client.start_workflow(
                OrderSupervisorWorkflow.run,
                run,
                id=workflow_id,
                task_queue=get_settings().task_queue,
                id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            )
        except WorkflowAlreadyStartedError as exc:
            raise WorkflowClosed(f"A supervisor workflow is already running for this order ({workflow_id})") from exc
        except RPCError as exc:
            raise _translate(exc, "start the workflow") from exc

    async def signal(self, workflow_id: str, name: str, arg: Any | None = None) -> None:
        client = await _client()
        handle: WorkflowHandle = client.get_workflow_handle(workflow_id)
        try:
            if arg is None:
                await handle.signal(name)
            else:
                await handle.signal(name, arg)
        except RPCError as exc:
            raise _translate(exc, "signal it") from exc

    async def is_running(self, workflow_id: str) -> bool:
        client = await _client()
        try:
            description = await client.get_workflow_handle(workflow_id).describe()
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                return False
            raise _translate(exc, "check its status") from exc
        return description.status == WorkflowExecutionStatus.RUNNING


_gateway: WorkflowGateway = TemporalGateway()


def get_gateway() -> WorkflowGateway:
    return _gateway
