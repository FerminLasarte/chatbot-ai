# Arquitectura

## Responsabilidad de cada carpeta del backend

```
apps/api/
├── app/
│   ├── main.py               Solo montaje: app, routers, middleware. Sin logica.
│   ├── core/
│   │   ├── config.py         Settings con pydantic-settings. Fuente unica de verdad.
│   │   ├── security.py       Firma HMAC de webhooks, auth del dashboard.
│   │   └── logging.py        Logging JSON con tenant_id en cada linea.
│   │
│   ├── api/v1/
│   │   ├── routes/
│   │   │   ├── chat.py       POST /chat — el endpoint del motor.
│   │   │   ├── tenants.py    CRUD de clientes (lo consume el dashboard).
│   │   │   ├── knowledge.py  Subida y listado de documentos.
│   │   │   └── webhooks.py   Entrada cruda de WhatsApp.
│   │   └── deps.py           ★ get_current_tenant() — resuelve de quien es el request.
│   │
│   ├── channels/             ★ Conectores. Traducen formato, nada mas.
│   │   ├── base.py           IncomingMessage + interfaz ChannelAdapter.
│   │   ├── whatsapp/
│   │   │   ├── client.py     Llamadas salientes a la Graph API de Meta.
│   │   │   └── parser.py     Payload de Meta -> IncomingMessage normalizado.
│   │   └── webchat/          Widget del sitio del cliente.
│   │
│   ├── ai/                   ★ Todo lo que toca el LLM.
│   │   ├── llm/client.py     Wrapper del SDK de Anthropic, manejo de refusals.
│   │   ├── prompts/
│   │   │   ├── base_system.py  Reglas del motor, iguales para todos. Versionadas.
│   │   │   ├── rag_answer.py   Como se inyecta el contexto recuperado.
│   │   │   └── builder.py      Compone base + prompt del tenant + contexto.
│   │   └── rag/
│   │       ├── ingest.py     Documento -> chunks -> embeddings -> DB.
│   │       ├── embedder.py   Texto -> vectores (proveedor intercambiable).
│   │       └── retriever.py  ★ Busqueda SIEMPRE filtrada por tenant_id.
│   │
│   ├── services/             Logica de negocio; orquesta todo lo anterior.
│   │   └── conversation.py   El flujo: recuperar -> componer prompt -> generar.
│   │
│   ├── models/               Tablas SQLAlchemy (tenant, document, chunk, ...).
│   ├── schemas/              Contratos Pydantic de la API.
│   ├── db/session.py         Engine y sesion async.
│   └── workers/              Tareas pesadas fuera del request (ingesta grande).
│
├── alembic/                  Migraciones. Nunca tocar la DB a mano.
└── tests/
```

## Las tres decisiones que definen si esto escala

### 1. El System Prompt de cada cliente vive en la base de datos

`app/ai/prompts/` guarda las plantillas **base** del motor: las reglas que aplican
a todos, versionadas en Git y revisables en PR. El prompt especifico de cada pyme
es la columna `tenants.system_prompt`, editable desde el dashboard sin desplegar.
`builder.py` los compone en runtime.

Si el prompt de cada cliente fuera un archivo, cada cambio de copy de un cliente
seria un deploy.

### 2. El aislamiento entre tenants es de una sola pieza

`deps.py::get_current_tenant()` resuelve el tenant desde la peticion y ese
`tenant_id` se propaga como dependencia hasta `retriever.py`. La busqueda vectorial
**nunca** corre sin `WHERE tenant_id = ?`.

Esta es la unica linea de codigo que, si falla, le muestra a un cliente los
documentos de otro. Cubierta por `tests/test_tenant_isolation.py`.

Los webhooks de WhatsApp no pasan por `get_current_tenant`: resuelven el tenant por
`phone_number_id`. Es el segundo punto de entrada del aislamiento y hay que
tratarlo con el mismo cuidado.

### 3. Los canales son adaptadores, no logica

`channels/whatsapp/` traduce el payload de Meta al formato interno y nada mas.
La respuesta del bot no cambia segun el canal. Cuando aparezca Instagram o un
widget web, se agrega una carpeta al lado en vez de meter `if channel == "whatsapp"`
en medio del servicio de conversacion.

## Autenticacion

No hay un solo consumidor de la API, hay tres con niveles de confianza distintos.
Conflacionarlos es el error de diseno a evitar.

| Scope | Quien | Puede | Donde vive la clave |
| --- | --- | --- | --- |
| `admin` | la agencia | crear/listar clientes, emitir y revocar claves | tu servidor |
| `tenant` | dashboard de un cliente | leer y editar SU config, subir SUS documentos | tu servidor |
| `chat` | widget web del cliente | solo `POST /chat` | **el navegador de cualquiera** |

**La clave `chat` es publica por naturaleza**: viaja en el JavaScript de la web
del cliente. Si compartiera credencial con el dashboard, cualquiera que abra el
inspector le podria editar el prompt y leer los documentos. Por eso tiene su
propio scope, y hay tests que verifican que no puede hacer nada mas.

`admin` **no** abre todas las puertas: una clave admin no tiene `tenant_id`, asi
que no puede usar los endpoints que operan sobre un cliente concreto (`/me`).
Es deliberado — obliga a decir explicitamente sobre que cliente se opera.

### Como se guardan

De la clave solo se persiste `sha256(clave)` mas un prefijo publico. El secreto
se muestra una unica vez, al emitirla.

**SHA-256 y no bcrypt/argon2, a proposito.** Esos algoritmos son lentos aposta
para frenar la fuerza bruta contra contrasenas humanas, que tienen poca entropia.
Una API key nuestra son 32 bytes de `secrets.token_urlsafe`: ~256 bits. No hay
fuerza bruta posible, asi que bcrypt no compraria seguridad — solo agregaria
~100 ms a cada request autenticado.

El prefijo (16 chars) permite encontrar la fila por indice en lugar de hashear
toda la tabla en cada request, y sirve para identificar la clave en el dashboard
sin revelarla. La comparacion del hash es en tiempo constante.

### Invariante en la base

Un `CHECK` garantiza que una clave `admin` no tenga `tenant_id` y que una clave
de cliente si lo tenga. Esta en la base y no solo en el codigo: se cumple aunque
alguien inserte con `psql`.

### Primera clave

Huevo y gallina: para emitir claves hace falta una clave admin. La primera sale
del CLI, que habla directo con la base:

```bash
uv run python -m app.cli crear-clave-admin --nombre "laptop de fermin"
```

> **Pendiente:** no hay login humano (email + contrasena) para que el duenio de
> la pyme entre solo al dashboard. Hoy el modelo asume que la agencia opera el
> dashboard y le emite claves al cliente. Cuando haga falta self-service, se
> agrega una tabla `users` y sesiones **encima** de esto; las API keys siguen
> siendo la via para el widget y las integraciones.

## Cuotas

Con precio plano a pymes, un cliente sin tope se puede comer la ganancia del mes.
Y la clave del widget viaja en el navegador: filtrada y puesta en un loop, quema
presupuesto de la agencia, no del cliente.

**Cuota y rate limiting no son lo mismo.** La cuota acota *cuanto* se gasta en
total (protege el margen); el rate limiting acota *que tan rapido* (protege
contra abuso y loops). Implementado hoy: solo la cuota.

### Chequeo e incremento son una sola sentencia

```sql
INSERT INTO tenant_usage (tenant_id, period, messages) VALUES (:t, :p, 1)
ON CONFLICT (tenant_id, period)
  DO UPDATE SET messages = tenant_usage.messages + 1
  WHERE tenant_usage.messages < :limite
RETURNING messages
```

Si no devuelve fila, la cuota esta agotada.

**No usar `leer contador -> decidir -> incrementar`.** Con la cuota en 1999/2000,
veinte peticiones simultaneas leen todas 1999, todas concluyen que hay lugar, y
terminas con 2019 mensajes cobrados. Hay un test que corre 20 peticiones
concurrentes contra un limite de 5: la version ingenua **pasa todos los tests
secuenciales** y falla solo ese.

### La cuota frena ANTES de gastar

`services/conversation.answer()` llama a `quota.consumir_mensaje()` como primera
linea, antes del retriever y del LLM. Si contara el consumo despues, la cuota no
protegeria nada: ya habrias pagado los embeddings y los tokens del mensaje que
rechazas. Hay un test que espia el cliente del LLM y verifica que el mensaje
rechazado nunca llega a el.

### Configuracion

`tenants.monthly_message_limit`: entero, o `NULL` para sin limite. Un cliente
nuevo nunca nace sin tope — se completa con `settings.default_monthly_message_limit`.
La migracion que introdujo la columna incluye un backfill por el mismo motivo:
sin el, todos los clientes existentes habrian quedado ilimitados justo en la
migracion que agrega las cuotas.

Solo la agencia (`admin`) cambia limites. El cliente ve su consumo en
`GET /tenants/me/usage` pero no se puede subir el techo.

Los tokens se acumulan aparte (`input`/`output`/`cache_read`) para facturar y
medir. No frenan nada: cuotear y facturar son ejes distintos.

> **Pendiente: rate limiting.** La cuota acota la perdida total, pero un loop
> puede quemarla en una hora. Falta un limite por minuto, que necesita Redis
> (ya esta en el compose, sin usar) y una decision de que hacer si Redis se cae:
> fail-open deja pasar todo, fail-closed corta el servicio.

## Garantias del webhook

Meta reintenta las entregas y espera un 200 rapido. De ahi salen dos requisitos
que el codigo tiene que cumplir, y que estan cubiertos por tests que se
verificaron rompiendo el arreglo a proposito.

### Idempotencia por reclamo atomico

Cada mensaje entrante se "reclama" en `processed_events` antes de procesarse:

```sql
INSERT INTO processed_events (channel, external_id, ...)
VALUES (...) ON CONFLICT DO NOTHING RETURNING id
```

Si no devuelve fila, otro proceso ya lo tomo: es una reentrega y se ignora.

**No usar `SELECT` y despues `INSERT`.** Dos entregas simultaneas del mismo
mensaje verian ambas "no existe" y las dos procesarian. La unicidad es sobre
`(channel, external_id)`, no sobre `external_id` solo: distintos canales pueden
usar el mismo ID.

### Ningun fallo silencioso

Le respondemos 200 a Meta enseguida, asi que el trabajo real ocurre en un
`BackgroundTasks`. Si algo falla ahi, Meta **ya no va a reintentar**. Por eso
`_handle` es una frontera de la que no puede escapar ninguna excepcion:

- El error queda en `processed_events.status = 'failed'` con el detalle, para
  poder encontrarlo (`WHERE status = 'failed'`) y reintentarlo.
- El usuario recibe un mensaje de cortesia. Un silencio es indistinguible de que
  el bot lo ignore.
- Generar la respuesta pero no poder entregarla **no** cuenta como exito: si
  `send_text` falla, el evento queda `failed`.

Los reintentos de fallos transitorios (red, 429, 5xx) viven en
`core/retry.py`, con backoff exponencial y jitter. Los 4xx no se reintentan:
un 401 no mejora por insistir. El SDK de Anthropic ya trae los suyos.

> **Limite conocido:** `BackgroundTasks` vive en el proceso. Si el contenedor se
> reinicia entre el 200 y el fin del procesamiento, ese mensaje queda en
> `pending` para siempre. Es visible y reintentable a mano, pero cuando el
> volumen lo justifique hay que mover esto a una cola real (Redis ya esta en el
> compose para eso).

## Orden del prompt y prompt caching

El caching de Anthropic es un match de **prefijo**: cualquier byte que cambie
invalida todo lo posterior. Por eso el prompt se arma en este orden:

| Posicion | Contenido              | Estabilidad        | Cache             |
| -------- | ---------------------- | ------------------ | ----------------- |
| 0        | `BASE_SYSTEM_PROMPT`   | identico a todos   | compartido global |
| 1        | `tenant.system_prompt` | estable por cliente| por tenant ← breakpoint |
| 2        | contexto RAG + pregunta| cambia siempre     | sin cache         |

El `cache_control` va en el bloque 1. El contexto recuperado va en el turno del
usuario, despues del breakpoint, para no invalidar nada.

Regla practica: **nunca interpolar fecha, hora, UUID ni nombre de usuario dentro
de los bloques 0 y 1**. Un `datetime.now()` ahi hace que el cache no acierte nunca.
Minimo cacheable en `claude-opus-5`: 512 tokens.

## Embeddings

Anthropic no expone un endpoint de embeddings. El RAG usa **Voyage AI** detras de
la interfaz `Embedder` en `ai/rag/embedder.py`, para poder cambiar de proveedor sin
tocar el resto del motor.

Cambiar de proveedor implica cambiar `EMBEDDINGS_DIM` y **regenerar todos los
vectores**: la columna `Vector(dim)` es de tamano fijo.
