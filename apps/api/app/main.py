"""Punto de entrada. Solo montaje: nada de logica de negocio aca."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routes import chat, knowledge, tenants, webhooks
from app.core.config import settings
from app.core.logging import setup_logging
from app.services.quota import QuotaExcedida


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(QuotaExcedida)
async def _quota_excedida(request: Request, exc: QuotaExcedida) -> JSONResponse:
    """429 en un unico lugar, en vez de un try/except en cada ruta.

    No aplica al webhook de WhatsApp: ahi el trabajo ocurre en background, fuera
    del ciclo request/response, y se maneja explicitamente.
    """
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "cuota mensual agotada",
            "limit": exc.limite,
            "period": exc.periodo,
        },
    )


app.include_router(chat.router, prefix="/api/v1")
app.include_router(tenants.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
