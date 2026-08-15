"""Punto de entrada. Solo montaje: nada de logica de negocio aca."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routes import (
    chat,
    conversations,
    incidents,
    knowledge,
    onboarding,
    portal,
    tenants,
    webhooks,
)
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.monitoreo import setup_monitoreo
from app.core.retry import RetryableHTTPError
from app.services.conversation import ConversacionAjena
from app.services.quota import QuotaExcedida

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    # Antes de aceptar la primera peticion: si algo explota al arrancar,
    # queremos que ese error tambien se reporte.
    setup_monitoreo()
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


@app.exception_handler(ConversacionAjena)
async def _conversacion_ajena(request: Request, exc: ConversacionAjena) -> JSONResponse:
    """404 y no 403: no confirmamos que la conversacion exista para otro cliente."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "conversacion no encontrada"},
    )


@app.exception_handler(RetryableHTTPError)
async def _proveedor_no_disponible(request: Request, exc: RetryableHTTPError) -> JSONResponse:
    """503 y no 500: el fallo es de un proveedor externo (rate limit o caida),
    no un bug nuestro, y reintentar mas tarde puede funcionar.

    Sin esto la excepcion sube sin manejar: FastAPI responde 500 con cuerpo de
    texto plano, y cualquier cliente que espere JSON rompe al parsearlo.
    """
    logger.warning("proveedor externo no disponible: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "el servicio esta sobrecargado en este momento, probá de nuevo"},
    )


app.include_router(chat.router, prefix="/api/v1")
app.include_router(tenants.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(incidents.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
# Sin API key: se autentica con el token firmado de la URL (ver el modulo).
app.include_router(onboarding.router, prefix="/api/v1")
# Lo usa el duenio del negocio, no la agencia: el tenant sale de la clave y
# nunca de la URL (ver el modulo).
app.include_router(portal.router, prefix="/api/v1")


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
