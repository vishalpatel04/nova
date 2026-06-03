"""Readiness endpoint tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_readiness_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/readiness")
    assert response.status_code == 200
    data = response.json()
    assert "ready" in data
    assert "checks" in data
    assert isinstance(data["checks"], list)

    db_check = next(c for c in data["checks"] if c["name"] == "database")
    assert db_check["status"] == "ok"
