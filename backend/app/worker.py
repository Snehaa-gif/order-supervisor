"""Temporal worker process: hosts the supervisor workflow and its activities.

Run with:  uv run python -m app.worker
"""

import asyncio
import logging

from temporalio.worker import Worker

from app.agent.llm import get_llm
from app.config import get_settings
from app.db.session import get_sessionmaker, init_db
from app.temporal_client import get_temporal_client
from app.workflows.activities import SupervisorActivities
from app.workflows.order_supervisor import OrderSupervisorWorkflow

logger = logging.getLogger("order_supervisor.worker")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    await init_db()
    llm = get_llm()
    activities = SupervisorActivities(llm=llm, sessions=get_sessionmaker())
    client = await get_temporal_client()
    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[OrderSupervisorWorkflow],
        activities=activities.all(),
    )
    logger.info("Worker started on task queue '%s' (LLM provider: %s)", settings.task_queue, llm.name)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
