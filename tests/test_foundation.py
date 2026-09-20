from importlib import import_module

from fastapi.testclient import TestClient
from ranah_api.main import app


def test_workspace_imports() -> None:
    for name in (
        "domain",
        "agents",
        "llm",
        "literature",
        "evidence",
        "review",
        "statistics",
        "documents",
        "workflow",
    ):
        assert import_module(f"ranah_{name}")
    assert import_module("ranah_worker_orchestration")


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
