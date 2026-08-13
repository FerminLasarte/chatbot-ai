"""Reporte de errores a Sentry.

POR QUE HACE FALTA
------------------
Los logs van a stdout y de ahi al visor de Railway. Eso sirve para investigar
algo que YA sabes que se rompio; no sirve para enterarte. El caso que mas duele
es el del webhook: procesa en `BackgroundTasks`, fuera del ciclo
request/respuesta, asi que un fallo ahi no le devuelve un error a nadie -queda
una fila `failed` en la base y silencio-.

QUE NO SE MANDA
---------------
★ Sentry es un proveedor mas que ve datos nuestros, y la politica de privacidad
que publicamos enumera a los proveedores por los que pasan los mensajes. Para
no tener que sumarlo a esa lista, esta configurado para que NO reciba contenido
de conversaciones:

  - `send_default_pii=False`: no manda cabeceras, cookies ni cuerpo del request.
  - `include_local_variables=False`: es el importante. Por defecto el SDK adjunta
    las variables locales de cada frame del stack trace, y ahi viajan el texto
    del usuario y la respuesta del modelo. Con esto queda solo el stack.

Lo que si viaja es el tenant_id, que dice A QUIEN se le rompio sin decir que
escribio. Es exactamente lo que hace falta para reaccionar.
"""

import logging

import sentry_sdk
from sentry_sdk.types import Event, Hint

from app.core.config import settings
from app.core.logging import tenant_id_ctx

logger = logging.getLogger(__name__)


def _etiquetar_con_tenant(evento: Event, hint: Hint) -> Event:
    """Agrega a que cliente pertenece el error, leyendo el ContextVar que ya
    usa el logging. Sin esto, un error dice que fallo pero no a quien."""
    tenant_id = tenant_id_ctx.get()
    if tenant_id:
        evento.setdefault("tags", {})["tenant_id"] = tenant_id
    return evento


def setup_monitoreo() -> None:
    """Arranca Sentry si hay DSN. Sin DSN no hace absolutamente nada.

    Mismo criterio que las credenciales de WhatsApp: la funcionalidad se activa
    cargando una variable de entorno, y el proyecto corre igual sin ella -en
    desarrollo y en los tests no queremos mandar nada a ningun lado-.
    """
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        send_default_pii=False,
        include_local_variables=False,  # ver el docstring: aca viajaria el mensaje
        # Muestreo de performance apagado: nos interesan los errores, y las
        # trazas de rendimiento son las que consumen la cuota del plan gratuito.
        traces_sample_rate=0.0,
        before_send=_etiquetar_con_tenant,
    )
    logger.info("reporte de errores activo (%s)", settings.environment)
