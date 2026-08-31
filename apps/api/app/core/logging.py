"""Logging estructurado. El tenant_id viaja en cada linea via ContextVar."""

import json
import logging
import re
import sys
from contextvars import ContextVar

tenant_id_ctx: ContextVar[str | None] = ContextVar("tenant_id", default=None)

# ★ Credenciales que no pueden terminar escritas en el log.
#
# No es teorico: httpx loguea en INFO la URL entera de cada llamada, y el canje
# del `code` del alta le manda a Meta el App Secret como query param. El
# resultado era el App Secret de la App -la credencial que firma TODAS las altas
# de TODOS los clientes- en texto plano en los logs de Railway, junto al code de
# autorizacion del cliente.
#
# El tachado va aca y no silenciando a httpx a proposito: esas lineas son las
# que dejan ver que paso con Meta cuando un alta falla, y se quieren conservar.
# Y va sobre el mensaje ya armado, asi que cubre tambien lo que loguee cualquier
# libreria de la que no controlamos el formato.
_CREDENCIALES = re.compile(
    r"(client_secret|access_token|auth_token|code)=[^&\s\"\']+", re.IGNORECASE
)


def tachar(texto: str) -> str:
    """Reemplaza el valor de cualquier credencial que aparezca en el texto."""
    return _CREDENCIALES.sub(r"\1=***", texto)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": tachar(record.getMessage()),
            "tenant_id": tenant_id_ctx.get(),
        }
        if record.exc_info:
            # El traceback tambien: una excepcion de httpx trae la URL adentro.
            payload["exc"] = tachar(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
