"""HTTP entry point; scientific work belongs in durable workers."""

import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.requests import Request

from ranah_api.projects import router

app = FastAPI(title="RanahResearch API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.environ.get("RANAH_WEB_ORIGIN", "http://127.0.0.1:3000"),
        "http://localhost:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {"code": "HTTP_ERROR", "message": str(exc.detail)}
    )
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "USER_INPUT_ERROR",
                "message": "; ".join(
                    f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}" for issue in exc.errors()
                ),
            }
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness only; this does not claim dependency readiness."""
    return {"status": "ok"}
