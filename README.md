# chatbot-ai

Motor de chatbot multi-tenant con IA para pymes. El nucleo es unico; cada cliente
tiene su propio System Prompt y su propia base de conocimiento.

## Stack

| Capa      | Tecnologia                                         |
| --------- | -------------------------------------------------- |
| Backend   | Python 3.12 + FastAPI + SQLAlchemy 2.0 (async)      |
| LLM       | Anthropic Claude (`claude-haiku-4-5`, ver `evals/`) |
| RAG       | Postgres + pgvector, embeddings de Voyage AI        |
| Frontend  | Next.js 16 (App Router) + TypeScript + Tailwind     |
| Canales   | WhatsApp Cloud API (Meta), widget web               |

## Estructura

```
apps/api/    Backend FastAPI (motor, RAG, canales)
apps/web/    Landing de la agencia + dashboard de clientes
infra/       docker-compose (Postgres+pgvector) y Dockerfiles
docs/        Arquitectura y ADRs
```

La responsabilidad de cada carpeta del backend esta documentada en
[docs/architecture.md](docs/architecture.md).

## Levantar el entorno

**1. Infraestructura**

```bash
docker compose -f infra/docker-compose.yml up -d
```

**2. Backend**

```bash
cd apps/api && cp .env.example .env && uv sync && uv run alembic upgrade head && uv run fastapi dev app/main.py
```

Queda en http://localhost:8000 — documentacion interactiva en `/docs`.

## Migraciones (Alembic)

La base **nunca** se toca a mano. Todo cambio de esquema pasa por una migracion
versionada y commiteada.

```bash
cd apps/api
uv run alembic upgrade head                              # aplicar pendientes
uv run alembic revision --autogenerate -m "descripcion"  # generar tras cambiar models/
uv run alembic downgrade -1                              # revertir la ultima
uv run alembic current                                   # en que revision esta la base
uv run alembic history --verbose                         # historial
```

La URL de conexion la inyecta `alembic/env.py` desde `app.core.config.settings`;
no esta hardcodeada en `alembic.ini`.

> **Revisar siempre lo que genera `--autogenerate`.** No es infalible: no detecta
> renombres (los ve como drop + create, lo que borra datos) ni algunos cambios de
> indice. `alembic/env.py` incluye un hook `render_item` para que emita bien el
> tipo `Vector` de pgvector, pero el indice HNSW de `chunks.embedding` hay que
> verificarlo a mano en cada revision que lo toque: sin ese indice la busqueda
> vectorial hace scan secuencial de toda la tabla, sin avisar.

**3. Frontend**

```bash
cd apps/web && npm run dev
```

Queda en http://localhost:3000.

## Calidad

```bash
cd apps/api && uv run ruff check . && uv run mypy app && uv run pytest
```

## Reglas del proyecto

- **El System Prompt de cada cliente vive en la base de datos**, no en archivos.
  `app/ai/prompts/` contiene solo las plantillas base del motor, versionadas en Git.
- **Toda busqueda vectorial filtra por `tenant_id`.** Ver `app/ai/rag/retriever.py`
  y el test en `tests/test_tenant_isolation.py`.
- **Los canales son adaptadores.** Traducen formatos; no contienen logica de negocio.
- **Nunca commitear `.env`.** Solo `.env.example` con las claves vacias.
