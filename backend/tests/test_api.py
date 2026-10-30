"""HTTP API tests with a fake Temporal gateway and a SQLite database."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.gateway import WorkflowClosed, WorkflowUnavailable, get_gateway
from app.api.routes import get_session
from app.domain import InstructionSignal, OrderEvent, RunInput
from app.main import create_app, seed_templates

pytestmark = pytest.mark.integration


class FakeGateway:
    def __init__(self) -> None:
        self.started: list[tuple[str, RunInput]] = []
        self.signals: list[tuple[str, str, Any]] = []
        self.fail_start = False
        self.signal_error: Exception | None = None
        self.running: set[str] = set()

    async def start(self, workflow_id: str, run: RunInput) -> None:
        if self.fail_start:
            raise WorkflowUnavailable("Temporal is not reachable")
        self.started.append((workflow_id, run))
        self.running.add(workflow_id)

    async def signal(self, workflow_id: str, name: str, arg: Any | None = None) -> None:
        if self.signal_error:
            raise self.signal_error
        self.signals.append((workflow_id, name, arg))

    async def is_running(self, workflow_id: str) -> bool:
        return workflow_id in self.running


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
async def client(sessions: async_sessionmaker[AsyncSession], gateway: FakeGateway, monkeypatch) -> AsyncIterator[AsyncClient]:
    from app.db import session as db_session

    monkeypatch.setattr(db_session, "get_sessionmaker", lambda: sessions)
    monkeypatch.setattr("app.main.session_scope", _scope_factory(sessions))
    await seed_templates()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_gateway] = lambda: gateway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


def _scope_factory(sessions: async_sessionmaker[AsyncSession]):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session
            await session.commit()

    return scope


async def start_run(client: AsyncClient, order_id: str = "ORD-1") -> dict[str, Any]:
    response = await client.post(
        "/api/runs",
        json={
            "supervisor_id": "tpl-standard",
            "order_id": order_id,
            "order_context": {"total": 10},
            "instructions": [" Be fast ", ""],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_templates_are_seeded(client: AsyncClient) -> None:
    response = await client.get("/api/supervisors")
    ids = {s["id"] for s in response.json()}
    assert {"tpl-standard", "tpl-vip", "tpl-risk"} <= ids


async def test_create_and_get_supervisor(client: AsyncClient) -> None:
    body = {
        "name": "Night shift",
        "base_instruction": "Watch the order carefully overnight.",
        "tools": ["create_internal_note", "escalate_issue", "create_internal_note"],
        "default_wake_minutes": 3,
        "max_sleep_minutes": 30,
        "wake_aggressiveness": "high",
        "model": "  ",
    }
    created = await client.post("/api/supervisors", json=body)
    assert created.status_code == 201
    data = created.json()
    assert data["tools"] == ["create_internal_note", "escalate_issue"]
    assert data["model"] is None
    fetched = await client.get(f"/api/supervisors/{data['id']}")
    assert fetched.json()["name"] == "Night shift"


async def test_create_supervisor_rejects_unknown_tool(client: AsyncClient) -> None:
    body = {"name": "x", "base_instruction": "long enough text", "tools": ["launch_rocket"]}
    response = await client.post("/api/supervisors", json=body)
    assert response.status_code == 422


async def test_start_run_starts_one_workflow_per_order(client: AsyncClient, gateway: FakeGateway) -> None:
    run = await start_run(client)
    assert run["status"] == "starting"
    assert gateway.started[0][0] == "order-supervisor-ORD-1"
    assert gateway.started[0][1].instructions == ["Be fast"]

    duplicate = await client.post("/api/runs", json={"supervisor_id": "tpl-standard", "order_id": "ORD-1"})
    assert duplicate.status_code == 409


async def test_start_run_marks_failed_when_temporal_down(client: AsyncClient, gateway: FakeGateway) -> None:
    gateway.fail_start = True
    response = await client.post("/api/runs", json={"supervisor_id": "tpl-standard", "order_id": "ORD-9"})
    assert response.status_code == 503
    runs = (await client.get("/api/runs")).json()
    assert runs[0]["status"] == "failed"


async def test_events_instructions_and_controls_are_signalled(client: AsyncClient, gateway: FakeGateway) -> None:
    run = await start_run(client)
    run_id = run["id"]

    assert (
        await client.post(f"/api/runs/{run_id}/events", json={"type": "warehouse_fire", "payload": {"x": 1}})
    ).status_code == 202
    assert (
        await client.post(f"/api/runs/{run_id}/instructions", json={"text": "Escalate delays", "wake_agent": True})
    ).status_code == 202
    for action in ("pause", "resume"):
        assert (await client.post(f"/api/runs/{run_id}/{action}")).status_code == 202
    assert (await client.post(f"/api/runs/{run_id}/interrupt", json={"note": "check now"})).status_code == 202
    assert (await client.post(f"/api/runs/{run_id}/terminate", json={"reason": ""})).status_code == 202

    names = [name for _, name, _ in gateway.signals]
    assert names == ["ingest_event", "add_instruction", "pause", "resume", "interrupt", "terminate"]
    event = gateway.signals[0][2]
    assert isinstance(event, OrderEvent) and event.type == "warehouse_fire"
    assert gateway.signals[1][2] == InstructionSignal(text="Escalate delays", wake_agent=True)
    assert gateway.signals[-1][2] == "Terminated by operator"


async def test_event_type_must_be_snake_case(client: AsyncClient) -> None:
    run = await start_run(client)
    response = await client.post(f"/api/runs/{run['id']}/events", json={"type": "Drop Table"})
    assert response.status_code == 422


async def test_unknown_run_returns_404(client: AsyncClient) -> None:
    assert (await client.get("/api/runs/nope")).status_code == 404
    assert (await client.post("/api/runs/nope/pause")).status_code == 404


async def test_run_detail_and_filters(client: AsyncClient) -> None:
    run = await start_run(client)
    detail = (await client.get(f"/api/runs/{run['id']}")).json()
    assert detail["timeline"] == [] and detail["tool_executions"] == []
    assert len((await client.get("/api/runs?active=true")).json()) == 1
    assert (await client.get("/api/runs?active=false")).json() == []


async def test_meta_lists_tools_and_events(client: AsyncClient) -> None:
    meta = (await client.get("/api/meta")).json()
    assert len(meta["action_tools"]) >= 4
    assert "payment_failed" in meta["event_types"]


async def test_timestamps_are_serialized_with_utc_offset(client: AsyncClient) -> None:
    run = await start_run(client)
    assert run["created_at"].endswith(("Z", "+00:00"))


async def test_open_run_whose_workflow_died_is_released(client: AsyncClient, gateway: FakeGateway) -> None:
    first = await start_run(client, "ORD-5")
    gateway.running.clear()  # the workflow was stopped outside the app

    second = await start_run(client, "ORD-5")

    assert second["id"] != first["id"]
    stale = (await client.get(f"/api/runs/{first['id']}")).json()
    assert stale["status"] == "failed"


async def test_signal_errors_map_to_409_or_503(client: AsyncClient, gateway: FakeGateway) -> None:
    run = await start_run(client)
    gateway.signal_error = WorkflowClosed("gone")
    assert (await client.post(f"/api/runs/{run['id']}/pause")).status_code == 409
    gateway.signal_error = WorkflowUnavailable("down")
    assert (await client.post(f"/api/runs/{run['id']}/pause")).status_code == 503


async def test_blank_instruction_and_oversized_payload_are_rejected(client: AsyncClient) -> None:
    run = await start_run(client)
    assert (await client.post(f"/api/runs/{run['id']}/instructions", json={"text": "   "})).status_code == 422
    huge = {"type": "customer_message_received", "payload": {"message": "x" * 9000}}
    assert (await client.post(f"/api/runs/{run['id']}/events", json=huge)).status_code == 422


async def test_database_allows_only_one_open_run_per_order(sessions) -> None:
    from sqlalchemy.exc import IntegrityError

    from app.db import repository as repo
    from app.templates import TEMPLATES

    async with sessions() as session:
        supervisor = await repo.create_supervisor(session, TEMPLATES[0], is_template=True)
        await repo.create_run(
            session, run_id="r1", order_id="O", supervisor=supervisor, workflow_id="w", order_context={}, instructions=[]
        )
        await session.commit()
        with pytest.raises(IntegrityError):
            await repo.create_run(
                session, run_id="r2", order_id="O", supervisor=supervisor, workflow_id="w", order_context={}, instructions=[]
            )
