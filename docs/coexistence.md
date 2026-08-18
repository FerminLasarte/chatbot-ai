# Coexistence: el comercio contesta a mano y el bot sigue andando

Estado: **investigado, sin implementar**. Este documento es el traspaso para la
sesion que lo implemente.

## Que problema resuelve

Hoy un numero conectado a la Cloud API es del bot y punto. Si el duenio del
comercio quiere contestar el mismo a un cliente, tiene que entrar a la bandeja
de Meta desde la web y ademas pausar el bot a mano desde el portal
(`POST /portal/conversations/{id}/manual`).

Coexistence es una funcion de Meta (GA desde mayo 2025) que permite que el
**mismo numero** este activo a la vez en la app de WhatsApp Business (el celular,
uso manual) y en la Cloud API (el bot), con sincronizacion en tiempo real.

Lo que compramos con esto:

- El comercio sigue usando su celular como siempre. No cambia de numero, no
  pierde chats ni contactos.
- Cuando contesta a mano, Meta nos avisa por webhook. El bot se puede callar
  **solo**, sin que nadie toque el portal.
- Argumento de venta mucho mas fuerte que "dame un numero nuevo para el bot".

## Como funciona del lado de Meta

Con coexistence activo, el WABA se suscribe a tres campos de webhook extra
ademas de `messages`:

| Campo | Que trae |
| --- | --- |
| `smb_message_echoes` | Los mensajes que el comercio manda **desde la app del celular**. Es el que nos importa. |
| `smb_app_state_sync` | Contactos actuales y nuevos de la app. |
| `history` | Backfill de hasta 180 dias de chats previos, en 3 fases (dia 0-1, 1-90, 90-180). Opcional. |

## Requisitos y limitaciones (lado Meta, no negociables)

- El numero tiene que estar **activo en la app WhatsApp Business** (no el
  WhatsApp comun) hace un tiempo. Minimo 7 dias de uso; Meta recomienda 1-2
  meses para no arriesgar que lo marquen. Un numero recien creado NO es elegible.
- App version >= 2.24.17, celular **con camara**: el alta pide escanear un QR.
- Hay que abrir la app al menos **cada 13 dias** o el puente se corta. Si el
  comercio delega todo al bot y deja el telefono en un cajon, se le desconecta.
- Throughput fijo de **5 mensajes por segundo** por numero. Irrelevante para
  nosotros: el bot contesta 1:1 y no hay envio masivo en el codigo. Solo
  molestaria con campanias masivas.
- No soporta la Marketing Messages Lite API. A tener en cuenta si algun dia
  vendemos "mandale una promo a toda tu base".
- Si el numero es nuevo y nunca paso por la app, NO usar el flujo de
  coexistence: va el Embedded Signup estandar, que es el que ya tenemos.

## Lo que ya esta hecho en el codigo (no rehacer)

La mitad dificil esta. El "modo manual" ya existe y funciona:

- `Conversation.pausada_hasta` + `Conversation.en_modo_manual()` en
  `apps/api/app/models/tenant.py:132`. Es fecha de vencimiento, no booleano, a
  proposito: un interruptor olvidado prendido deja al comercio mudo para siempre
  y en silencio.
- El unico punto de control esta en `apps/api/app/api/v1/routes/webhooks.py`,
  dentro de `_handle`: si `conversacion.en_modo_manual()`, guarda el entrante con
  `conversation.registrar_entrante` y sale sin llamar al modelo. **Esta rama no
  hay que tocarla.**
- `conversaciones.pausar(db, tenant_id, conversation_id, horas=...)` y
  `conversaciones.reanudar(...)` en `apps/api/app/services/conversaciones.py`.
- Default de horas: `settings.manual_mode_hours` (8).
- Tests: `apps/api/tests/test_modo_manual.py`.

Lo unico que falta es que la pausa se dispare **sola** cuando el humano contesta
desde el celular, en vez de a mano desde el portal.

## Lo que hay que implementar

### 1. Configuracion en el Meta App Dashboard (no es codigo)

Crear/ajustar la configuracion de Embedded Signup para onboarding de usuarios de
la app de WhatsApp Business, y suscribir el WABA a `smb_message_echoes` (y
`smb_app_state_sync` / `history` si se decide usarlos).

★ DUDA ABIERTA: no esta confirmado si coexistence necesita un `config_id`
distinto del actual (`settings.whatsapp_config_id`, uno solo hoy). Si necesita
uno propio, hay que decidir si se reemplaza o si el onboarding soporta los dos
caminos (numero nuevo -> flujo actual; numero que ya usa la app -> coexistence).
Esto cambia el alcance del punto 4.

### 2. `apps/api/app/channels/whatsapp/parser.py`

Hoy `parse_incoming` solo mira `value["messages"]` y devuelve `None` para todo
lo demas — o sea, un echo hoy se ignora en silencio.

Hay que agregar el reconocimiento de `smb_message_echoes`. Como el dataclass
`IncomingMessage` (`apps/api/app/channels/base.py`) no distingue direccion,
probablemente convenga:

- un tipo nuevo (`OutgoingEcho` o similar) o un campo `direccion` en
  `IncomingMessage`, y
- que `parse_incoming` devuelva algo que el webhook pueda ramificar.

★ DUDA ABIERTA: **no tenemos confirmada la forma exacta del JSON de
`smb_message_echoes`**. No escribir el parser a ciegas: activar coexistence en un
numero de prueba, loguear el payload crudo que llega, y recien ahi escribirlo.

### 3. `apps/api/app/api/v1/routes/webhooks.py`

Cuando llega un echo (mensaje que mando el humano desde el celular):

1. Resolver la conversacion con `conversation.resolver_conversacion(...)` usando
   el numero del **destinatario** (el cliente final), no el del comercio.
2. Guardar el mensaje con rol `assistant` (`ROL_ASISTENTE` en
   `services/conversation.py:38`), para que el historial que ve el modelo cuando
   retome incluya lo que dijo la persona. Hoy `registrar_entrante` solo guarda
   con rol `user`; hace falta el equivalente para el lado saliente.
3. Llamar a `conversaciones.pausar(...)` con `settings.manual_mode_hours`.
   Repetir la llamada corre el vencimiento, asi que cada mensaje manual estira
   la pausa sola — que es exactamente el comportamiento que queremos.

★ TRAMPA CRITICA: hay que verificar si los mensajes que manda **nuestro propio
bot** por la Cloud API tambien generan un evento `smb_message_echoes`. Si lo
hicieran y no se filtran, el bot se auto-pausaria con su propia respuesta y
dejaria de contestar para siempre. La documentacion dice que los echoes son de
mensajes enviados desde la app, pero **esto hay que confirmarlo con el payload
real antes de mergear**. Si hace falta filtrar, el discriminador candidato es el
id del mensaje (los nuestros los conocemos al enviar) o algun campo tipo
`smb_app_id` en el payload.

★ IDEMPOTENCIA: los echoes tienen su propio id de mensaje. Pasan por
`inbox.claim(db, channel, external_id, tenant_id)`, que tiene unique en
`(channel, external_id)`. Verificar que un echo no colisione con el id del
mensaje entrante original. Si hiciera falta, usar un `channel` distinto
(`"whatsapp_echo"`) para separar los espacios de ids.

### 4. Onboarding (`apps/web/src/app/onboarding/` + `apps/api/.../onboarding`)

Depende de lo que se resuelva en el punto 1. Como minimo, el flujo actual asume
un solo camino; con coexistence el alta pasa a requerir el celular del duenio en
la mano (QR). El link de onboarding deberia abrirse desde el celular o al lado
de la persona.

Ver `apps/api/app/services/whatsapp.py:113` (canje -> suscripcion -> registro).
`registrar_numero` ya contempla el caso de migrar un numero que venia de la app.

## Dudas para resolver antes de escribir codigo

1. Forma exacta del payload de `smb_message_echoes`. **Bloqueante** para el
   parser. Se resuelve activando coexistence en un numero de prueba y logueando.
2. Si los envios del propio bot generan echo. **Bloqueante**: define si hace
   falta filtro anti-auto-pausa.
3. Si coexistence necesita su propio `config_id` en el Meta App Dashboard.
4. Si los tenants ya dados de alta con el Embedded Signup estandar pueden sumar
   coexistence sobre el mismo numero, o si hay que re-onboardearlos.
5. Si Meta cuenta la antiguedad desde el uso del WhatsApp comun o desde la
   conversion a WhatsApp Business app. Afecta a un comercio que recien convierte.

## Fuentes

- <https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users/>
- <https://docs.360dialog.com/docs/resources/phone-numbers/coexistence>
- <https://docs.360dialog.com/partner/onboarding/whatsapp-coexistence/coexistence-webhooks>
- <https://docs.360dialog.com/docs/hub/embedded-signup/coexistence-onboarding>
