# Coexistence: el comercio contesta a mano y el bot sigue andando

Estado: **PRENDIDO en produccion desde el 2026-08-31**
(`COEXISTENCE_ENABLED=true` en el servicio `api` de Railway), verificado de
punta a punta con el numero de Argencore. Lo que se comprobo contra produccion
esta en "Como quedo", al final.

★ Antes de dar de alta un cliente nuevo por coexistence, leer "La trampa de los
mensajes automaticos": es la unica configuracion del lado del comercio que hay
que tocar, y si se pasa por alto deja al bot mudo sin que nadie se entere.

Tres de las dudas que bloqueaban esto quedaron resueltas contra la
documentacion oficial de Meta (consultada el 2026-08-18, ver Fuentes):

- **La forma del payload de `smb_message_echoes` esta confirmada** y coincide
  con lo que implementa el parser: lista `message_echoes`, con `from` / `to` /
  `id` / `timestamp` / `type` y el contenido bajo la clave del tipo.
- **La Cloud API NO genera echoes.** Los dispara la app del celular y los
  dispositivos companion, no nuestros envios. La trampa de la auto-pausa no se
  puede dar por ese camino; las dos defensas quedan igual, como seguro barato.
- **No hace falta un `config_id` propio.** Coexistence se activa solo cuando la
  cuenta cumple los requisitos de partner: la pantalla de seleccion de WABA
  pasa a ofrecer conectar una cuenta de WhatsApp Business existente.

★ REQUISITO NUEVO, y es el que puede frenar todo: Meta pide ser **Solution
Partner o Tech Provider**. No es un toggle, es un estado de la cuenta. Si no lo
somos, no importa cuan elegible sea el numero.

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
- Throughput fijo de **20 mensajes por segundo** por numero (Meta lo subio de
  los 5 que decia esta nota antes; verificado el 2026-08-26). Irrelevante para
  nosotros: el bot contesta 1:1 y no hay envio masivo en el codigo. Solo
  molestaria con campanias masivas.
- El cliente tiene **24 horas** desde que arranca el Embedded Signup para
  terminar el alta. Pasado ese plazo hay que empezar de cero.
- No soporta la Marketing Messages Lite API. A tener en cuenta si algun dia
  vendemos "mandale una promo a toda tu base".
- Si el numero es nuevo y nunca paso por la app, NO usar el flujo de
  coexistence: va el Embedded Signup estandar, que es el que ya tenemos.

## Sobre que se apoya: el modo manual, que ya existia

Coexistence no invento la pausa, solo la dispara sola. El "modo manual" ya
estaba y no se toco:

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

## Lo que ya esta implementado

Todo el lado del codigo, detras de `COEXISTENCE_ENABLED` (default `false`).

**El interruptor** — `settings.coexistence_enabled`. Apagado, un echo que llegue
se registra CRUDO en el log y no se actua sobre el. Ese log es justamente como
se confirma la forma real del payload sin arriesgar nada.

**Lectura del payload** — `parse_echo` en
`apps/api/app/channels/whatsapp/parser.py`, sobre un tipo nuevo `OutgoingEcho`
(`channels/base.py`). Lee campo por campo y con `.get()`: cualquier forma que no
entienda devuelve `None` y queda crudo en el log, en vez de actuar sobre una
lectura equivocada. Acepta la lista como `message_echoes` o como `messages`,
porque la forma exacta sigue sin confirmarse y equivocarse en ese nombre
significaria ignorar en silencio todos los mensajes manuales.

**`parse_incoming` ahora filtra por el nombre del campo.** Antes leia cualquier
`value["messages"]`. Un payload de echo tiene una forma bastante parecida: sin
el filtro, el bot podia leer como pregunta de un cliente algo que escribio el
propio duenio, contestarsela y cobrarle el turno. Los payloads sin `field`
siguen entrando, asi que no rompe nada de lo que ya andaba.

**El efecto** — `_recibir_echo` y `_handle_echo` en
`apps/api/app/api/v1/routes/webhooks.py`: resuelven la conversacion por el
numero del DESTINATARIO, guardan el mensaje con rol `assistant`
(`conversation.registrar_saliente`) y llaman a `conversaciones.pausar(...)` con
`settings.manual_mode_hours`. Cada mensaje manual corre el vencimiento, asi que
la pausa se estira sola mientras la persona sigue contestando. Un fallo aca NO
manda mensaje de cortesia al cliente final: seria meter al bot justo donde se le
pidio que no se meta.

**Las dos defensas contra la auto-pausa.** Era la trampa critica del plan
original: si Meta hiciera echo tambien de los mensajes que enviamos por la Cloud
API, el bot se pausaria con su propia respuesta y no volveria a contestar nunca.
Estan las dos porque no sabemos todavia si el caso existe:

1. *Por id.* `send_text` ahora devuelve el wamid, y cada envio nuestro lo deja
   anotado con `inbox.registrar_propio` en el canal `whatsapp_echo`. Cuando
   llegue el echo de ese mismo mensaje, `claim` falla y se descarta como
   duplicado. Es el mecanismo de la idempotencia usado al reves: en vez de
   recordar lo ya procesado, se anticipa lo que no hay que procesar.
2. *Por texto.* `conversation.coincide_con_la_ultima_respuesta`: si el echo es
   palabra por palabra lo ultimo que dijo el bot, se descarta y se loguea en
   WARNING. Cubre la carrera en la que el echo llega antes de que se anote el id.
   Si ese warning aparece seguido en produccion, significa que Meta SI hace echo
   de nuestros envios y que el filtro por id no los esta cubriendo.

**Idempotencia** — los echoes van por el canal `whatsapp_echo`, con espacio de
ids separado del entrante. La duda de si podian colisionar queda resuelta por
construccion.

Tests: `apps/api/tests/test_coexistence.py` (32 casos).

## La trampa de los mensajes automaticos

La app WhatsApp Business tiene mensaje de bienvenida y mensaje de ausencia, y
los manda sola. Para Meta son mensajes salientes del comercio como cualquier
otro, asi que **generan echo**. Con coexistence prendido, ese saludo automatico
hace exactamente lo que hace una respuesta a mano: pausa el bot 8 horas.

El modo de fallar es el peor posible. Entra un cliente nuevo, la app le manda el
saludo, el bot se calla, y nadie se entera hasta que el cliente se queja. Se
detecto el 2026-08-31 leyendo los echoes crudos ANTES de prender la variable: el
segundo echo que llego decia "Gracias por comunicarte con Argencore Solutions.
En unos minutos un asesor respondera tu consulta".

**En cada alta por coexistence hay que apagarlos** en el celular del comercio:
Ajustes -> Herramientas para la empresa -> Mensaje de bienvenida y Mensaje de
ausencia. No hay forma de distinguirlos en el payload: para Meta son iguales a
un mensaje escrito a mano.

## Como quedo (verificado en produccion el 2026-08-31)

**El payload es el que asumia el parser.** El echo real se paso por `parse_echo`
tal cual salio del log: devuelve el `to_number`, el texto, el `phone_number_id`
y el wamid, y `parse_incoming` lo ignora. La forma tiene campos de mas que la
hipotesis (`contacts`, `to_user_id`, `user_id`) y no molestan porque el parser
lee con `.get()`. No hubo que corregir nada.

**La Cloud API NO hace echo de lo que manda el bot.** Es la duda que mas
preocupaba, porque el bot pausandose con su propia respuesta lo dejaba mudo para
siempre. Con la funcion prendida y trafico real no aparecio ni una vez
`echo identico a la ultima respuesta del bot`. Las dos defensas quedan igual,
como seguro barato.

**La pausa funciona.** En el log de una prueba real, en orden: dos mensajes
entrantes contestados por el bot; despues
`respuesta manual desde el celular: bot pausado en esta conversacion`; y a
partir de ahi `conversacion en modo manual: mensaje guardado sin responder` por
cada mensaje del cliente. Cada respuesta manual corre el vencimiento.

**El registro del numero falla, y esta bien.** Meta contesta
`Register endpoint is not available for SMB businesses`: un numero que viene de
la app ya quedo registrado por ese vinculo. El alta lo reconoce y no lo reporta
como advertencia (ver `_es_alta_de_coexistence` en `services/whatsapp.py`).

**Para apagarlo**, `COEXISTENCE_ENABLED=false` en Railway: el bot vuelve a
ignorar los echoes al toque y nada mas cambia.

## Dudas que quedan abiertas

Las dos primeras de la lista original ya no lo son: somos Tech Provider
(aprobado el 2026-08-18) y el payload quedo confirmado contra produccion.

1. Si los tenants ya dados de alta con el Embedded Signup estandar pueden sumar
   coexistence sobre el mismo numero, o si hay que re-onboardearlos.
2. Si Meta cuenta la antiguedad desde el uso del WhatsApp comun o desde la
   conversion a WhatsApp Business app. Afecta a un comercio que recien convierte.
3. Cuanto tarda en la practica el backfill de `history` y si conviene pedirlo:
   en el alta de Argencore se acepto compartir hasta 6 meses de chats, y el
   webhook los ignora callado.

## Fuentes

- <https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users/>
- <https://docs.360dialog.com/docs/resources/phone-numbers/coexistence>
- <https://docs.360dialog.com/partner/onboarding/whatsapp-coexistence/coexistence-webhooks>
- <https://docs.360dialog.com/docs/hub/embedded-signup/coexistence-onboarding>
