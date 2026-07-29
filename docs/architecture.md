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
