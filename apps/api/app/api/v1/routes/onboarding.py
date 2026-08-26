"""Alta de WhatsApp por parte del cliente, sin credenciales ni panel.

Estas dos rutas son las UNICAS de la API que no piden API key: la autorizacion
es el token firmado que viene en la URL (ver services/onboarding.py). El cliente
no tiene usuario en el panel —el panel es de la agencia— y la idea del flujo es
justamente que no tenga que tener uno: abre el link, se loguea con Facebook,
elige su numero y termino.

El alcance del token es a proposito minimo: deja ver el nombre del cliente y
conectarle un WhatsApp si todavia no tiene. Nada mas.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from app.api.v1.deps import DbSession
from app.channels.whatsapp.client import AltaWhatsAppError
from app.core.cifrado import CifradoNoConfigurado
from app.core.config import settings
from app.core.retry import RetryableHTTPError
from app.models.tenant import Tenant
from app.schemas.chat import OnboardingConectar, OnboardingEstado, OnboardingResultado
from app.services import onboarding, whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


async def _tenant_del_token(db: DbSession, token: str) -> Tenant:
    """Resuelve el cliente al que apunta el link, o corta con un error legible.

    Los mensajes de error de aca los lee el cliente final, no un desarrollador:
    tienen que decirle que hacer ("pedile uno nuevo"), no que fallo por dentro.
    """
    try:
        tenant_id = onboarding.verificar(token)
    except onboarding.LinkVencido as exc:
        raise HTTPException(status.HTTP_410_GONE, str(exc)) from exc
    except onboarding.LinkInvalido as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    tenant = await db.get(Tenant, tenant_id)
    # Un cliente borrado o desactivado deja el link muerto aunque el token siga
    # siendo valido: el token es un permiso, no una garantia de que haya destino.
    if tenant is None or not tenant.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "este link ya no esta disponible")
    return tenant


@router.get("/{token}", response_model=OnboardingEstado)
async def ver_estado(token: str, db: DbSession) -> OnboardingEstado:
    """Lo que necesita la pagina para dibujarse y para abrir el popup."""
    tenant = await _tenant_del_token(db, token)

    # Si falta la config de la App, el boton abriria un popup que muere con un
    # error de Facebook imposible de interpretar para el cliente. Mejor cortar
    # aca, que el error lo vea la agencia y no el cliente.
    if not settings.whatsapp_app_id or not settings.whatsapp_config_id:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "el alta de WhatsApp todavia no esta configurada del lado de la agencia",
        )

    return OnboardingEstado(
        nombre_cliente=tenant.name,
        app_id=settings.whatsapp_app_id,
        config_id=settings.whatsapp_config_id,
        api_version=settings.whatsapp_signup_api_version,
        ya_conectado=whatsapp.tiene_whatsapp(tenant),
    )


@router.post("/{token}/conectar", response_model=OnboardingResultado)
async def conectar(token: str, payload: OnboardingConectar, db: DbSession) -> OnboardingResultado:
    """Termina el alta con lo que devolvio el popup de Facebook."""
    tenant = await _tenant_del_token(db, token)

    # ★ No se pisa un WhatsApp ya conectado. Es lo que hace que un link filtrado
    # no pueda robarle el canal a un cliente que ya esta andando: para cambiar de
    # numero hay que desconectarlo primero desde el panel de la agencia.
    if whatsapp.tiene_whatsapp(tenant):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "este cliente ya tiene un WhatsApp conectado. Para cambiarlo, "
            "avisale a quien te paso el link.",
        )

    try:
        alta = await whatsapp.conectar_desde_signup(
            db,
            tenant,
            code=payload.code,
            waba_id=payload.waba_id,
            phone_number_id=payload.phone_number_id,
        )
    except whatsapp.NumeroYaAsignado as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except CifradoNoConfigurado as exc:
        # Falta ENCRYPTION_KEY: es un problema de la agencia, no del cliente.
        logger.error("alta imposible: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "no se pudo completar el alta por un problema de configuracion. "
            "Avisale a quien te paso el link.",
        ) from exc
    except (AltaWhatsAppError, RetryableHTTPError) as exc:
        # Nada quedo guardado (ver el orden en services/whatsapp.py), asi que el
        # cliente puede volver a intentar con el mismo link.
        logger.warning("fallo el alta del cliente %s: %s", tenant.id, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Meta rechazo la conexion. Proba de nuevo; si vuelve a fallar, "
            "avisale a quien te paso el link.",
        ) from exc

    logger.info("cliente %s conecto WhatsApp por Embedded Signup", tenant.id)
    return OnboardingResultado(conectado=True, advertencia=alta.advertencia)
