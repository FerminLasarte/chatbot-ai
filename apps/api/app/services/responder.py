"""Contestar a mano desde el panel o desde el portal.

QUE PROBLEMA RESUELVE
---------------------
Hasta ahora, ver que alguien pidio una persona y efectivamente atenderlo eran
dos programas distintos: el hilo se leia en el panel y la respuesta se escribia
en la app de WhatsApp del celular. En el medio hay un cambio de dispositivo, y
ahi es donde se pierden las derivaciones.

Igual que el resto de `services/`, este modulo no decide de quien es la
peticion: recibe el tenant ya resuelto por la credencial de quien llama.

★ LAS TRES COSAS QUE PASAN JUNTAS, Y POR QUE NINGUNA SE PUEDE SALTEAR
---------------------------------------------------------------------
1. Se anota el id del mensaje que devolvio Meta como YA PROCESADO.

   Con coexistence prendido, Meta nos hace echo de todo lo que sale del numero
   del negocio, incluido lo que mandamos nosotros. Ese echo llega al webhook
   indistinguible de un mensaje que el duenio escribio desde el celular. Sin
   este paso, el bot ve su propia respuesta como "contesto una persona", se
   pausa solo, y encima duplica el mensaje en el hilo (ver
   `inbox.registrar_propio` y docs/coexistence.md).

2. Se guarda el mensaje con `autor="persona"`.

   El rol es `assistant` porque para el cliente final esto es "me contesto el
   negocio", igual que una respuesta del bot. La diferencia vive en `autor`, y
   es la que permite auditar despues quien dijo que.

3. Se pausa el bot y se da por atendida la derivacion.

   Contestar a mano es la forma mas fuerte que existe de decir "esto lo atiendo
   yo": si el bot siguiera respondiendo, le pisaria la respuesta a la persona
   en la misma conversacion. Y no alcanza con confiar en la pausa automatica de
   coexistence, porque el paso 1 justamente hace que ese echo no llegue.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp import client
from app.core.config import settings
from app.models.tenant import Conversation, Tenant
from app.schemas.chat import MessageRead
from app.services import conversaciones, inbox, whatsapp
from app.services.conversation import AUTOR_PERSONA, ROL_ASISTENTE, guardar_mensaje

logger = logging.getLogger(__name__)

CANAL_WHATSAPP = "whatsapp"


class NoSePuedeResponder(Exception):
    """No se puede mandar esta respuesta, y el mensaje explica por que.

    Es un solo tipo para todos los motivos a proposito: los cuatro terminan en
    el mismo lugar -un cartel arriba de la caja de texto- y lo unico que cambia
    es que dice. Un arbol de excepciones aca obligaria a cada ruta a traducir
    cuatro casos para escribir el mismo 409.
    """


def _revisar_ventana(conversacion: Conversation, minutos_de_ventana: int | None) -> None:
    """★ Se comprueba ANTES de llamar a Meta, no despues del rechazo.

    Meta contesta un 4xx cuando la ventana esta cerrada, asi que sin esto el
    error igual aparece —pero recien despues de que alguien escribio la
    respuesta entera, y con el texto de Meta, en ingles y hablando de
    plantillas. Con la ventana resuelta de este lado, el panel puede apagar la
    caja de texto de entrada y decir en castellano que paso.
    """
    if minutos_de_ventana is None:
        raise NoSePuedeResponder(
            "todavia no escribio nadie en esta conversacion, asi que no hay a quien contestarle"
        )
    if minutos_de_ventana <= 0:
        raise NoSePuedeResponder(
            f"pasaron mas de {conversaciones.HORAS_DE_VENTANA} h desde el ultimo mensaje del "
            "cliente y WhatsApp ya no deja mandar texto libre. Tiene que volver a escribir el, "
            "o hay que usar una plantilla aprobada por Meta."
        )


async def responder(
    db: AsyncSession,
    tenant: Tenant,
    conversation_id: uuid.UUID,
    texto: str,
) -> MessageRead:
    """Manda un mensaje al cliente final en nombre del negocio.

    Levanta `ConversacionNoEncontrada` si el hilo no existe o es de otro
    cliente, y `NoSePuedeResponder` cuando el envio no corresponde.
    """
    conversacion = await conversaciones.buscar(db, tenant.id, conversation_id)

    if conversacion.channel != CANAL_WHATSAPP:
        raise NoSePuedeResponder("por ahora solo se puede contestar por WhatsApp desde aca")

    # El estado ya calculado del hilo: de ahi sale si la ventana sigue abierta.
    estado = await conversaciones.detalle(db, conversacion)
    _revisar_ventana(conversacion, estado.minutos_de_ventana)

    token = whatsapp.leer_token(tenant)
    if not token or not tenant.whatsapp_phone_number_id:
        raise NoSePuedeResponder(
            "este cliente todavia no tiene WhatsApp conectado, asi que no se puede enviar nada"
        )

    # ★ Primero se envia y despues se guarda. Al reves, un fallo de Meta dejaria
    # en el hilo un mensaje que el cliente final nunca recibio, que es la peor
    # de las dos mentiras posibles: quien atiende se queda esperando una
    # respuesta a algo que no llego a decir.
    wamid = await client.send_text(
        to=conversacion.external_id,
        text=texto,
        phone_number_id=tenant.whatsapp_phone_number_id,
        access_token=token,
    )

    # Paso 1 del docstring del modulo. Va antes de guardar porque el echo puede
    # llegar en milisegundos, y llegar antes de que el id este anotado es
    # exactamente el caso que rompe.
    if wamid:
        await inbox.registrar_propio(db, CANAL_WHATSAPP, wamid, tenant.id)
    else:
        # Meta acepto el envio pero no devolvio el id (ver client._id_del_mensaje).
        # El mensaje salio igual; lo que se degrada es la deteccion del echo.
        logger.warning(
            "respuesta manual enviada sin wamid: el echo podria pausar el bot solo",
            extra={"tenant_id": str(tenant.id), "conversacion_id": str(conversacion.id)},
        )

    await guardar_mensaje(db, conversacion.id, ROL_ASISTENTE, texto, AUTOR_PERSONA)

    ahora = datetime.now(UTC)
    conversacion.last_activity_at = ahora
    conversacion.pausada_hasta = ahora + timedelta(hours=settings.manual_mode_hours)
    # Contestar es atender: la derivacion deja de estar pendiente. Mismo criterio
    # que `conversaciones.reanudar`, donde reactivar el bot a mano tambien la da
    # por atendida.
    conversacion.derivada_at = None
    await db.commit()

    # El mensaje recien guardado, para que quien llamo lo pinte en el hilo sin
    # tener que volver a pedir todo.
    mensajes = await conversaciones.listar_mensajes(db, tenant.id, conversacion.id, limite=1)
    return mensajes[-1]
