# Imagen de produccion de la API.
#
# Build en dos etapas: las dependencias se instalan en una capa aparte que solo
# se rehace cuando cambian pyproject.toml/uv.lock. Cambiar codigo de la app no
# reinstala nada, y el deploy pasa de minutos a segundos.

FROM python:3.12-slim AS builder

# uv resuelve e instala con el lockfile, igual que en local y en CI: la imagen
# queda con exactamente las mismas versiones que se testearon.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Solo el manifiesto primero: es lo que define esta capa cacheable.
COPY pyproject.toml uv.lock ./
# --no-dev: pytest, ruff y mypy no tienen nada que hacer en la imagen final.
RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.12-slim AS runtime

# Usuario sin privilegios: si alguien logra ejecutar codigo dentro del
# contenedor, no lo hace como root.
RUN useradd --create-home --uid 1000 app

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app . .

USER app

EXPOSE 8000

# El hosting inyecta $PORT y espera que escuchemos ahi; 8000 es el fallback
# para correr la imagen a mano.
#
# Las migraciones corren aca, en el arranque del contenedor, y no en un paso
# separado del deploy: garantiza que el esquema esta al dia antes de aceptar la
# primera peticion. `sh -c` es necesario para que $PORT se expanda.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
