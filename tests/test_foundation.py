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
    ):
        assert import_module(f"ranah_{name}")


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
