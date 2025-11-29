import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.app.main import app


@pytest.fixture(scope="session")
def db_url():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set for integration tests")
    return url


@pytest.fixture(scope="session")
def engine(db_url):
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Database not reachable: {exc}")
    return engine


@pytest.fixture(autouse=True)
def clean_db(engine):
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE pipeline_runs CASCADE"))
    yield


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def test_post_events_upsert_and_get(client):
    payload = [
        {
            "build_id": "build-1001",
            "branch": "main",
            "result": "success",
            "start_time": "2025-09-28T10:15:00Z",
            "end_time": "2025-09-28T10:18:42Z",
            "repo_name": "repo1",
            "commit_sha": "abc123",
        },
        {
            "build_id": "build-1002",
            "branch": "feature/login-refactor",
            "result": "failed",
            "start_time": "2025-09-28T11:02:10Z",
            "end_time": "2025-09-28T11:04:10Z",
            "repo_name": "repo2",
            "commit_sha": "def456",
        },
    ]
    resp = client.post("/events", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 2
    assert all("idempotency_key" in item for item in data)

    # Upsert same payload should not create duplicates
    resp2 = client.post("/events", json=payload)
    assert resp2.status_code == 201
    assert resp2.json()[0]["id"] == data[0]["id"]

    # GET events returns items with duration_seconds
    events = client.get("/events").json()
    assert len(events) == 2
    assert all("duration_seconds" in item for item in events)


def test_stats_and_health(client):
    health = client.get("/health")
    assert health.status_code == 200

    # Insert one run
    client.post(
        "/events",
        json={
            "build_id": "build-2001",
            "branch": "main",
            "result": "success",
            "start_time": "2025-09-28T10:15:00Z",
            "end_time": "2025-09-28T10:18:42Z",
        },
    )
    summary = client.get("/stats/summary").json()
    assert "counts_by_result" in summary
