"""SQLAlchemy tables. Column types are portable so the test suite can run on SQLite."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON, datetime: DateTime(timezone=True)}  # noqa: RUF012


class SupervisorRow(Base):
    __tablename__ = "supervisors"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    base_instruction: Mapped[str] = mapped_column(Text)
    tools: Mapped[list[Any]]
    default_wake_minutes: Mapped[int] = mapped_column(Integer)
    max_sleep_minutes: Mapped[int] = mapped_column(Integer)
    wake_aggressiveness: Mapped[str] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(80))
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


OPEN_RUN_CONDITION = text("status NOT IN ('completed', 'terminated', 'failed')")


class RunRow(Base):
    __tablename__ = "runs"
    # At most one open supervisor run per order, enforced by the database even under concurrent requests.
    __table_args__ = (
        Index(
            "uq_runs_one_open_per_order",
            "order_id",
            unique=True,
            postgresql_where=OPEN_RUN_CONDITION,
            sqlite_where=OPEN_RUN_CONDITION,
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    supervisor_id: Mapped[str] = mapped_column(ForeignKey("supervisors.id"))
    supervisor_name: Mapped[str] = mapped_column(String(120))
    # Not unique: a closed order may be supervised again later under the same workflow id.
    workflow_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    order_status: Mapped[str] = mapped_column(String(32))
    order_context: Mapped[dict[str, Any]]
    memory_summary: Mapped[str] = mapped_column(Text, default="")
    next_wake_at: Mapped[datetime | None]
    wake_guidance: Mapped[dict[str, Any]] = mapped_column(default=dict)
    instructions: Mapped[list[Any]] = mapped_column(default=list)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_events: Mapped[int] = mapped_column(Integer, default=0)
    final_report: Mapped[dict[str, Any] | None]
    close_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None]


class TimelineRow(Base):
    __tablename__ = "timeline_entries"
    __table_args__ = (Index("ix_timeline_run_at", "run_id", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    at: Mapped[datetime]
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    important: Mapped[bool] = mapped_column(Boolean, default=False)


class ToolExecutionRow(Base):
    """Simulated side effects (the 'outbox'). The idempotency key makes activity retries safe."""

    __tablename__ = "tool_executions"

    idempotency_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[str] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict[str, Any]]
    result: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
