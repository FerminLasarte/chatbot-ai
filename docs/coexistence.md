# Coexistence: el comercio contesta a mano y el bot sigue andando

Estado: **codigo implementado y apagado por defecto** (`COEXISTENCE_ENABLED=false`).
Falta la configuracion del lado de Meta. Lo que queda por hacer esta al final,
en "Como prenderlo".

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

## Lo que falta

### 1. Configuracion en el Meta App Dashboard (no es codigo)

Suscribir el WABA a los **tres** campos: `smb_message_echoes`, `history` y
`smb_app_state_sync`. Meta los pide todos para coexistence, aunque el codigo
solo actua sobre el primero.

★ RESUELTO EN CODIGO (2026-08-26). Lo que abre el asistente de coexistence no
es una opcion del dashboard sino el `featureType` del `FB.login`, en
`apps/web/src/app/onboarding/[token]/conectar.tsx`. Iba en `""` para todos, que
es el asistente estandar: a un comercio que venia a conectar SU numero, Meta le
ofrecia dar de alta un numero virtual nuevo, sin ninguna opcion de usar el
propio. Ahora el link pregunta cual de los dos caminos quiere y manda
`whatsapp_business_app_onboarding` o `""` segun la respuesta. El valor viejo
`coexistence` ya no existe del lado de Meta.

Los tres campos: `smb_message_echoes` (el unico que usa el codigo), mas
`history` y `smb_app_state_sync`. Estos dos ultimos el webhook los ignora
callado a proposito (`CAMPOS_CONOCIDOS_SIN_USO`): el backfill de `history` son
hasta 180 dias de chats, y avisar por cada uno dejaria el log inservible justo
durante el alta.

RESUELTO: no hace falta un `config_id` propio. Sirve el que ya esta en
`settings.whatsapp_config_id`.

### 2. Confirmar el payload contra un evento real

La forma ya esta confirmada contra la documentacion (arriba), asi que esto pasa
de ser un bloqueante a ser una verificacion. Mandar un mensaje a mano desde el
celular y buscar en el log de Railway:

    echo de coexistence recibido con la funcion apagada: {...}

Comparar ese JSON con `_payload_echo` en `tests/test_coexistence.py`, que es la
hipotesis que implementa el parser. Si difiere, corregir los dos.

En la misma prueba conviene confirmar lo que dice la documentacion sobre la
Cloud API: mandar un mensaje CON el bot y verificar que NO aparece un segundo
log de echo con esa respuesta. Si apareciera, la documentacion estaria
desactualizada y las dos defensas pasarian de seguro a mecanismo principal.

### 3. Onboarding (`apps/web/src/app/onboarding/` + `apps/api/.../onboarding`)

HECHO (2026-08-26). El link ya no asume un solo camino: pregunta si el numero es
el que ya se usa en la app WhatsApp Business o si es uno nuevo, y de ahi sale el
`featureType`. La pregunta no tiene default a proposito — los dos caminos son
irreversibles para el cliente y ninguno es el "normal".

Sigue en pie que el alta por coexistence **requiere el celular del duenio en la
mano** (escanea un QR), asi que el link conviene abrirlo desde el celular o al
lado de la persona.

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

1. Si somos -o podemos ser- Solution Partner o Tech Provider. Es el requisito
   que puede frenar todo el plan, y no depende del codigo.
2. Si los tenants ya dados de alta con el Embedded Signup estandar pueden sumar
   coexistence sobre el mismo numero, o si hay que re-onboardearlos.
3. Si Meta cuenta la antiguedad desde el uso del WhatsApp comun o desde la
   conversion a WhatsApp Business app. Afecta a un comercio que recien convierte.

## Fuentes

- <https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users/>
- <https://docs.360dialog.com/docs/resources/phone-numbers/coexistence>
- <https://docs.360dialog.com/partner/onboarding/whatsapp-coexistence/coexistence-webhooks>
- <https://docs.360dialog.com/docs/hub/embedded-signup/coexistence-onboarding>
