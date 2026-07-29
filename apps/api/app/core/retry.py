"""Reintentos con backoff exponencial para llamadas HTTP salientes.

Solo se reintenta lo que tiene sentido reintentar: errores de red, 429 y 5xx.
Un 400 o un 401 no mejoran por insistir — se propagan de una.

El SDK de Anthropic ya trae reintentos propios (429 y 5xx, 2 por defecto), asi
que esto es para las llamadas que hacemos con httpx a mano: Voyage y Meta.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

REINTENTABLES = {408, 409, 429, 500, 502, 503, 504}


class RetryableHTTPError(Exception):
    """Fallo transitorio que agoto los reintentos."""


async def with_retry[T](
    fn: Callable[[], Awaitable[T]],
    *,
    intentos: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    descripcion: str = "llamada http",
) -> T:
    ultimo: Exception | None = None

    for intento in range(1, intentos + 1):
        try:
            return await fn()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in REINTENTABLES:
                raise  # 4xx del cliente: reintentar no arregla nada
            ultimo = exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            ultimo = exc

        if intento == intentos:
            break

        # Backoff exponencial con jitter, para no sincronizar reintentos
        # de muchos mensajes que fallaron a la vez.
        espera = min(base_delay * 2 ** (intento - 1), max_delay)
        espera *= 0.5 + random.random()  # noqa: S311  (no es criptografico)
        logger.warning(
            "%s fallo (intento %d/%d), reintentando en %.1fs: %s",
            descripcion,
            intento,
            intentos,
            espera,
            ultimo,
        )
        await asyncio.sleep(espera)

    raise RetryableHTTPError(f"{descripcion} fallo tras {intentos} intentos: {ultimo}") from ultimo
