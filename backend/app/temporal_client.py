"""Shared Temporal client (pydantic-aware data converter)."""

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from app.config import get_settings

_client: Client | None = None


async def get_temporal_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
            data_converter=pydantic_data_converter,
        )
    return _client


def workflow_id_for_order(order_id: str) -> str:
    """One workflow per order: the order id *is* the workflow identity."""
    return f"order-supervisor-{order_id}"
