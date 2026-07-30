# Evals

Compara modelos de Anthropic sobre el mismo caso de uso real: una peluqueria
ficticia (`fixtures/peluqueria_rosa.txt`) con 30 preguntas (`cases.py`) que
cubren precios/horarios en el documento, alucinaciones, memoria conversacional,
temas fuera de alcance, inyeccion de instrucciones, y tono.

No es un test de CI. Hace llamadas reales y pagas a Anthropic y Voyage, así que
corre solo cuando lo pedís vos.

## Requisitos

`ANTHROPIC_API_KEY` y `VOYAGE_API_KEY` completas en `apps/api/.env`, y Postgres
levantado (`docker compose -f infra/docker-compose.yml up -d`).

## Uso

```bash
cd apps/api
uv run python -m evals.run
uv run python -m evals.run --models claude-opus-5,claude-haiku-4-5
uv run python -m evals.run --out evals/reports/mi_corrida.md
```

Imprime el progreso caso por caso, un resumen en la terminal, y escribe un
reporte completo en `evals/reports/<fecha>.md` con la respuesta de cada modelo
a cada pregunta, para leer a mano.

## Como leer el resultado

Cada caso tiene uno de dos tipos de verificacion:

- **Automatica** (`espera_contener` / `espera_no_contener` / `espera_regex` /
  `espera_no_regex` en `cases.py`): solo para lo objetivamente verificable — un
  precio, un horario, una palabra clave. Se ve como ✅/❌ en el reporte.
- **Manual** (sin esos campos): tono, juicio, resistencia a inyeccion. Aparece
  como 👁️ y hay que leer la respuesta. **La mayoria de lo que importa en un
  chatbot de atencion al cliente es de este tipo** — no hay forma barata de
  automatizarlo sin agregar otro modelo como juez, que suma costo y otro punto
  de falla opaco.

El numero que mas vale la pena mirar primero: cuantos casos de `alucinacion`
fallaron. Un chatbot que inventa un precio es un problema comercial, no un
detalle tecnico.

## Que reutiliza y que no

Reutiliza el pipeline real: `ai.rag.retriever.search`, `ai.prompts.builder`, y
`ai.llm.client.complete` — el mismo codigo que corre en produccion. La unica
diferencia con `services.conversation.answer()` es que el eval no persiste
conversaciones ni consume cuota (no tiene sentido cuotear una corrida de
prueba), y sube el documento una sola vez en vez de una vez por modelo, porque
la recuperacion no depende de que modelo va a responder despues.

## Agregar un modelo de Anthropic

Una linea: agregalo a `PRECIOS_USD_POR_MTOK` en `run.py` con su precio de
entrada/salida por millon de tokens, y pasalo en `--models`.

## Agregar otro proveedor (OpenAI, Gemini)

Esto **no es una linea** — y si en algun momento se dijo que lo era, esta
sección lo corrige. `ai/llm/client.py` es un wrapper del SDK de Anthropic;
`run.py` cambia de modelo pisando `settings.llm_model`, pero eso solo mueve la
aguja dentro de un mismo proveedor.

Agregar OpenAI o Gemini implica escribir un adaptador nuevo -una funcion que
reciba `(system_blocks, messages)` en la misma forma y devuelva algo con
`.text`, `.input_tokens`, `.output_tokens`- usando el SDK de ese proveedor. Es
codigo nuevo y acotado (no toca el resto del pipeline: `search()` y
`build_system_blocks()`/`build_user_turn()` se siguen reutilizando igual), pero
no es gratis. Cuando haya claves de OpenAI o Gemini, se arma esa pieza.
