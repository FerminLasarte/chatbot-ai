"""El log no puede llevarse puestas las credenciales.

★ Esto no es una precaucion teorica: httpx loguea en INFO la URL entera de cada
llamada, y el canje del `code` del alta manda el App Secret como query param.
Durante un alta real quedo escrito en los logs de Railway el App Secret de la
App -la credencial que firma las altas de TODOS los clientes- junto con el code
de autorizacion del cliente.
"""

import json
import logging

from app.core.logging import JsonFormatter, tachar

SECRETO = "35cb32e79efb2f87eff1dcedf6f794fd"
CODE = "AQIjyRkSRgaCZuncM_FLFWnE5k85Jd6"


def _formatear(mensaje: str, *args: object) -> str:
    registro = logging.LogRecord("httpx", logging.INFO, __file__, 1, mensaje, args, None)
    return json.loads(JsonFormatter().format(registro))["message"]


def test_la_url_del_canje_no_deja_el_app_secret_en_el_log() -> None:
    url = (
        "https://graph.facebook.com/v21.0/oauth/access_token"
        f"?client_id=1815429283231759&client_secret={SECRETO}&code={CODE}"
    )
    salida = _formatear('HTTP Request: GET %s "HTTP/1.1 200 OK"', url)

    assert SECRETO not in salida
    assert CODE not in salida
    # Lo demas se conserva: estas lineas son las que dejan ver que paso con Meta
    # cuando un alta falla.
    assert "graph.facebook.com" in salida
    assert "client_id=1815429283231759" in salida
    assert "200 OK" in salida


def test_tambien_se_tacha_el_access_token() -> None:
    assert "EAAG" not in tachar("GET /v21.0/me?access_token=EAAGsecretisimo")


def test_el_traceback_tampoco_lo_filtra() -> None:
    try:
        raise RuntimeError(f"fallo pidiendo ?client_secret={SECRETO}")
    except RuntimeError:
        import sys

        registro = logging.LogRecord(
            "app", logging.ERROR, __file__, 1, "exploto", None, sys.exc_info()
        )
        salida = JsonFormatter().format(registro)

    assert SECRETO not in salida


def test_un_mensaje_sin_credenciales_queda_igual() -> None:
    mensaje = "cliente 1159779d conecto WhatsApp por Embedded Signup"
    assert _formatear(mensaje) == mensaje
