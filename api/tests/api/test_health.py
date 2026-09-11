"""``GET /api/healthz`` — the compose healthcheck's contract."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_db


def test_healthz_ok_when_database_answers(client: TestClient) -> None:
    response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class _BrokenSession:
    """Stands in for a session whose server has gone away."""

    def execute(self, *args: Any, **kwargs: Any) -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


@pytest.fixture
def broken_client(app: FastAPI) -> TestClient:
    app.dependency_overrides[get_db] = lambda: _BrokenSession()
    return TestClient(app)


def test_healthz_503_when_database_unreachable(broken_client: TestClient) -> None:
    response = broken_client.get("/api/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "error"}
