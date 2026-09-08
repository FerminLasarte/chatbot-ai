"""El portal del duenio: sus conversaciones, pausar su bot y editar su ficha.

QUE ES ESTO
-----------
El cliente de la agencia no tiene usuario en el panel —el panel es de la
agencia, con una contrasena compartida que ve a TODOS los clientes—. Pero
necesita poder hacer tres cosas por su cuenta, sin llamar a nadie: mirar quien
le escribio, callar al bot en una conversacion para atenderla el mismo, y
corregir los datos de su negocio cuando cambian.

Estas rutas son exactamente esas tres cosas y ninguna mas.

★ POR QUE NO HAY `tenant_id` EN NINGUNA URL DE ESTE ARCHIVO
-----------------------------------------------------------
Las rutas de la agencia (routes/conversations.py) dicen sobre que cliente operan
en el path, porque una clave admin no tiene cliente propio. Aca seria un agujero:
el cliente final es quien manda la peticion, asi que un `tenant_id` en la URL es
un dato que el elige. Bastaria con cambiar el UUID para leerle las
conversaciones al negocio de al lado.

En cambio el tenant sale de `CurrentTenant`, que lo saca de la fila de la clave
en la base (ver deps.py). No hay parametro que cruzar: para ver los datos de
otro cliente habria que tener la clave de otro cliente.

QUE PUEDE HACER EL QUE TENGA LA CLAVE
-------------------------------------
Listar las conversaciones de SU negocio, correr la fecha de `pausada_hasta` de
una de ellas, y leer y reescribir la ficha de datos de su negocio. No lee
documentos, no toca el prompt, no ve el consumo ni el tope, no puede borrar
conversaciones y no puede emitir ni revocar claves.

★ ESCRIBIR LA FICHA ES EL PERMISO MAS FUERTE QUE TIENE ESTA CLAVE, y se sumo a
sabiendas. Antes, el peor caso de una clave filtrada era que un tercero viera
los telefonos y los adelantos de los mensajes de ese negocio y le pausara el bot
unas horas —molesto y reversible—. Ahora tambien puede cambiar lo que el bot le
CONTESTA a los clientes de ese negocio: precios, horarios, envios.

Se acepto porque la alternativa —que cada cambio de horario pase por la
agencia— es lo que hoy hace que el producto no escale, y porque el dano sigue
acotado al negocio duenio de la clave, es visible (se ve en la ficha) y
reversible. El remedio es el mismo de siempre y es inmediato: la agencia emite
otro link desde el panel, y el anterior deja de servir en el acto.

Lo que la clave sigue SIN poder tocar es el `system_prompt` y los documentos:
la ficha entra al modelo como dato entre etiquetas (ver `ai/prompts/negocio.py`),
no como instrucciones.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import CurrentTenant, DbSession, PortalKey
from app.core.config import settings
from app.schemas.chat import (
    ConversationRead,
    ManualModeStart,
    MessageRead,
    PortalTenant,
    RespuestaManual,
)
from app.schemas.negocio import FichaNegocio
from app.services import conversaciones, ficha, responder

router = APIRouter(prefix="/portal", tags=["portal"])


def _no_encontrada() -> HTTPException:
    """404 tambien cuando la conversacion existe pero es de otro cliente.

    Un 403 confirmaria que ese id existe en algun lado, que es justo lo que no
    hace falta que sepa quien esta probando ids.
    """
    return HTTPException(status.HTTP_404_NOT_FOUND, "conversacion no encontrada")


@router.get("/me", response_model=PortalTenant)
async def mi_negocio(tenant: CurrentTenant, _: PortalKey) -> PortalTenant:
    """El nombre del negocio, para encabezar la pagina y confirmar el link.

    Tambien es la ruta que usa el frontend para validar la clave al canjearla
    por una cookie de sesion: si esto responde 200, el link sirve.
    """
    return PortalTenant(nombre=tenant.name)


@router.get("/conversations", response_model=list[ConversationRead])
async def mis_conversaciones(
    tenant: CurrentTenant,
    db: DbSession,
    _: PortalKey,
    limite: int = Query(default=50, ge=1, le=200),
) -> list[ConversationRead]:
    """Las conversaciones del propio negocio, la ultima primero."""
    return await conversaciones.listar(db, tenant.id, limite=limite)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
async def mi_conversacion(
    conversation_id: uuid.UUID,
    tenant: CurrentTenant,
    db: DbSession,
    _: PortalKey,
    limite: int = Query(default=200, ge=1, le=500),
) -> list[MessageRead]:
    """El hilo completo, para poder ver que se dijo y no solo el ultimo mensaje."""
    try:
        return await conversaciones.listar_mensajes(db, tenant.id, conversation_id, limite=limite)
    except conversaciones.ConversacionNoEncontrada as exc:
        raise _no_encontrada() from exc


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def responder_yo_mismo(
    conversation_id: uuid.UUID,
    payload: RespuestaManual,
    tenant: CurrentTenant,
    db: DbSession,
    _: PortalKey,
) -> MessageRead:
    """El duenio del negocio le contesta a su cliente sin salir del portal.

    ★ Esto AMPLIA lo que puede hacer una clave de portal filtrada: antes el
    peor caso era leer y pausar; ahora es escribirle a los clientes del negocio
    en nombre del negocio. Se acepto porque es exactamente para lo que existe
    el portal -que el duenio atienda- y porque el dano sigue acotado a su
    propio negocio, es visible en el hilo y el remedio es inmediato: la agencia
    emite otro link y el anterior deja de servir en el acto.

    Lo que sigue sin poder: escribirle a un cliente que no le escribio primero.
    La ventana de 24 h de Meta lo impide, y se comprueba antes de enviar.
    """
    try:
        return await responder.responder(db, tenant, conversation_id, payload.texto)
    except conversaciones.ConversacionNoEncontrada as exc:
        raise _no_encontrada() from exc
    except responder.NoSePuedeResponder as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/conversations/{conversation_id}/manual", response_model=ConversationRead)
async def pausar_mi_bot(
    conversation_id: uuid.UUID,
    payload: ManualModeStart,
    tenant: CurrentTenant,
    db: DbSession,
    _: PortalKey,
) -> ConversationRead:
    """Silencia al bot en esa conversacion para atenderla a mano.

    El tope de una semana lo valida el schema, igual que para la agencia: no
    existe la pausa indefinida (ver `Conversation.pausada_hasta`).
    """
    horas = payload.horas if payload.horas is not None else settings.manual_mode_hours
    try:
        return await conversaciones.pausar(db, tenant.id, conversation_id, horas=horas)
    except conversaciones.ConversacionNoEncontrada as exc:
        raise _no_encontrada() from exc


@router.delete("/conversations/{conversation_id}/manual", response_model=ConversationRead)
async def reanudar_mi_bot(
    conversation_id: uuid.UUID,
    tenant: CurrentTenant,
    db: DbSession,
    _: PortalKey,
) -> ConversationRead:
    """Devuelve la conversacion al bot antes de que venza la pausa."""
    try:
        return await conversaciones.reanudar(db, tenant.id, conversation_id)
    except conversaciones.ConversacionNoEncontrada as exc:
        raise _no_encontrada() from exc


# ---------------------------------------------------------------------------
# La ficha del negocio
#
# Sin `tenant_id` en la URL, igual que todo lo de arriba: el tenant sale de la
# clave. Un id en el path seria un dato que elige quien manda la peticion.
# ---------------------------------------------------------------------------


@router.get("/ficha", response_model=FichaNegocio)
async def mi_ficha(tenant: CurrentTenant, _: PortalKey) -> FichaNegocio:
    """Los datos que el bot sabe del negocio. Vacia si nunca cargo nada."""
    return ficha.leer(tenant)


@router.put("/ficha", response_model=FichaNegocio)
async def guardar_mi_ficha(
    payload: FichaNegocio, tenant: CurrentTenant, db: DbSession, _: PortalKey
) -> FichaNegocio:
    """Reemplaza la ficha entera y devuelve como quedo.

    PUT y no PATCH a proposito: el formulario manda la ficha completa, y un
    merge parcial sobre listas dejaria sin forma de BORRAR un horario o un
    bloque. La ultima escritura gana; con dos editores posibles —el duenio y la
    agencia— y cambios cada varios meses, no hace falta mas.

    El cliente ve el efecto en la respuesta siguiente del bot: la ficha se
    compone en el prompt, no hace falta desplegar nada.
    """
    return await ficha.guardar(db, tenant, payload)
