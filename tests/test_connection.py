"""
Tests for POST /api/connections/test using an SQLite provider
(no real Postgres or MySQL required in CI).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_connection_sqlite_url(client: AsyncClient, tmp_path) -> None:
    db_file = tmp_path / "test.db"
    resp = await client.post(
        "/api/connections/test",
        json={
            "database_type": "sqlite",
            "connection_method": "url",
            "database_url": f"sqlite:///{db_file}",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_connection_invalid_type(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/connections/test",
        json={
            "database_type": "oracle",   # not yet implemented
            "connection_method": "url",
            "database_url": "oracle://localhost/xe",
        },
    )
    # Returns 501 Not Implemented
    assert resp.status_code in (400, 501)


@pytest.mark.asyncio
async def test_connection_missing_url(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/connections/test",
        json={
            "database_type": "postgres",
            "connection_method": "url",
            # database_url intentionally omitted
        },
    )
    assert resp.status_code == 422
