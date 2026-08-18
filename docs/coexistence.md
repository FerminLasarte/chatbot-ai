# Coexistence: el comercio contesta a mano y el bot sigue andando

Estado: **codigo implementado y apagado por defecto** (`COEXISTENCE_ENABLED=false`).
Falta la configuracion del lado de Meta y confirmar el payload real contra un
numero de prueba. Lo que queda por hacer esta al final, en "Como prenderlo".

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

Tests: `apps/api/tests/test_coexistence.py` (25 casos).

## Lo que falta

### 1. Configuracion en el Meta App Dashboard (no es codigo)

Crear/ajustar la configuracion de Embedded Signup para onboarding de usuarios de
la app de WhatsApp Business, y suscribir el WABA a `smb_message_echoes` (y
`smb_app_state_sync` / `history` si se decide usarlos).

★ DUDA ABIERTA: no esta confirmado si coexistence necesita un `config_id`
distinto del actual (`settings.whatsapp_config_id`, uno solo hoy). Si necesita
uno propio, hay que decidir si se reemplaza o si el onboarding soporta los dos
caminos (numero nuevo -> flujo actual; numero que ya usa la app -> coexistence).
Esto cambia el alcance del punto 3.

### 2. Confirmar el payload real

Es lo unico que bloquea el prendido. Activar coexistence en un numero de prueba,
mandar un mensaje a mano desde el celular y buscar en el log de Railway:

    echo de coexistence recibido con la funcion apagada: {...}

Comparar ese JSON con `_payload_echo` en `tests/test_coexistence.py`, que es la
hipotesis que implementa el parser. Si difiere, corregir los dos.

En la misma prueba se responde la otra duda: mandar un mensaje CON el bot (que
conteste solo) y ver si aparece un segundo log de echo con ese mismo mensaje.
Si aparece, Meta hace echo de los envios por Cloud API y las dos defensas de
arriba pasan de ser un seguro a ser el mecanismo principal.

### 3. Onboarding (`apps/web/src/app/onboarding/` + `apps/api/.../onboarding`)

Sin tocar: depende de lo que se resuelva en el punto 1. Como minimo, el flujo
actual asume un solo camino; con coexistence el alta pasa a requerir el celular
del duenio en la mano (QR). El link de onboarding deberia abrirse desde el
celular o al lado de la persona.

Ver `apps/api/app/services/whatsapp.py:113` (canje -> suscripcion -> registro).
`registrar_numero` ya contempla el caso de migrar un numero que venia de la app.

## Como prenderlo

1. Configurar el lado de Meta (punto 1) en un numero de prueba.
2. Confirmar el payload con el log (punto 2) y corregir el parser si difiere.
3. `COEXISTENCE_ENABLED=true` en las variables de Railway. No hay que tocar
   codigo ni migrar nada.
4. Mirar el log por un dia. Si aparece
   `echo identico a la ultima respuesta del bot`, la defensa por id no esta
   funcionando y hay que revisarla antes de sumar mas clientes.

Para apagarlo, la variable vuelve a `false` y el bot ignora los echoes al toque.

## Dudas que quedan abiertas

1. Si coexistence necesita su propio `config_id` en el Meta App Dashboard.
2. Si los tenants ya dados de alta con el Embedded Signup estandar pueden sumar
   coexistence sobre el mismo numero, o si hay que re-onboardearlos.
3. Si Meta cuenta la antiguedad desde el uso del WhatsApp comun o desde la
   conversion a WhatsApp Business app. Afecta a un comercio que recien convierte.

## Fuentes

- <https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users/>
- <https://docs.360dialog.com/docs/resources/phone-numbers/coexistence>
- <https://docs.360dialog.com/partner/onboarding/whatsapp-coexistence/coexistence-webhooks>
- <https://docs.360dialog.com/docs/hub/embedded-signup/coexistence-onboarding>
