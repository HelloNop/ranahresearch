"""HTTP entry point; scientific work belongs in durable workers."""

from fastapi import FastAPI

app = FastAPI(title="RanahResearch API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness only; this does not claim dependency readiness."""
    return {"status": "ok"}
