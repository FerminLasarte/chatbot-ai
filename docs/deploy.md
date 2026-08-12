# Despliegue en Railway

El repo ya tiene todo lo necesario para desplegar: `Dockerfile` y `railway.json`
en `apps/api/` y `apps/web/`. Las dos imagenes estan construidas y probadas
localmente. Lo que queda son los pasos que requieren tu cuenta.

## Que se despliega

| Servicio | Que es | Root Directory en Railway |
| --- | --- | --- |
| Postgres | Base de datos (con pgvector) | — (se agrega desde el catalogo) |
| API | Backend FastAPI, el motor | `apps/api` |
| Web | Frontend Next.js | `apps/web` |

---

## 1. Base de datos

En Railway: **New → Database → Add PostgreSQL**.

Railway inyecta la variable `DATABASE_URL` con el formato `postgresql://...`.
La app la normaliza sola al driver async que necesita SQLAlchemy, asi que se
usa tal cual, sin editarla (ver el validador en `app/core/config.py`).

**Verificar pgvector.** El motor no arranca sin la extension `vector`. La
primera migracion la crea con `CREATE EXTENSION IF NOT EXISTS vector`, pero eso
solo funciona si la imagen de Postgres la tiene disponible. Si el primer deploy
de la API falla con `could not open extension control file` o
`type "vector" does not exist`, la imagen de Postgres no la trae: hay que usar
una imagen con pgvector (Railway tiene una plantilla de `pgvector` en su
catalogo) en vez de la de Postgres a secas.

## 2. API

**New → GitHub Repo →** este repo. Despues, en Settings del servicio:

- **Root Directory**: `apps/api`
- **Networking → Generate Domain** (necesario: sin dominio publico no hay HTTPS,
  y WhatsApp lo va a exigir mas adelante)

### Variables de entorno

| Variable | Valor |
| --- | --- |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (referencia al servicio de Postgres) |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `JWT_SECRET` | generalo con `openssl rand -hex 32` |
| `CORS_ORIGINS` | `["https://TU-WEB.up.railway.app"]` — la URL del servicio Web, con https |
| `ANTHROPIC_API_KEY` | tu clave de Anthropic |
| `VOYAGE_API_KEY` | tu clave de Voyage |
| `ENCRYPTION_KEY` | cifra el token de WhatsApp de cada cliente (ver `.env.example`) |
| `WHATSAPP_VERIFY_TOKEN` | el que pusiste en Meta al registrar el webhook |
| `WHATSAPP_APP_SECRET` | Meta -> Configuracion de la App -> Basica |
| `WHATSAPP_APP_ID` | Meta -> panel de la App |
| `WHATSAPP_CONFIG_ID` | Meta -> WhatsApp -> Configuracion -> Embedded Signup |
| `ONBOARDING_BASE_URL` | `https://TU-WEB.up.railway.app` — la URL del servicio Web, con https |

`LLM_MODEL` y `EMBEDDINGS_MODEL` no hace falta setearlas: los defaults del
codigo (`claude-haiku-4-5` y `voyage-4`) son los que elegimos con el eval.

**Si la config es insegura, la API se niega a arrancar** (secreto de ejemplo,
`DEBUG=true`, CORS con `*` o `http://`, o `ONBOARDING_BASE_URL` sin https). Es a
proposito: un servidor que levanta con secretos de ejemplo parece que anda y el
agujero recien se nota cuando alguien lo usa. El mensaje de error dice
exactamente que corregir.

★ `ONBOARDING_BASE_URL` es la que mas facil se olvida, y **bloquea el arranque**:
su default es `http://localhost:3000`, que no pasa la validacion de produccion.
Apunta al servicio **Web**, no a la API: la pagina de onboarding vive en el panel.

### Migraciones

Corren solas en cada arranque del contenedor (`alembic upgrade head` en el
`CMD`), antes de aceptar la primera peticion. No hay paso manual.

## 3. Web

Otro servicio desde el mismo repo. En Settings:

- **Root Directory**: `apps/web`
- **Networking → Generate Domain**

### Variables de entorno

| Variable | Valor | Llega al navegador? |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://TU-API.up.railway.app` | si |
| `NEXT_PUBLIC_API_KEY` | clave del tenant de demo (ver aviso) | **si** |
| `API_URL` | `https://TU-API.up.railway.app` | no |
| `ADMIN_API_KEY` | tu clave admin | no |
| `PANEL_PASSWORD` | la contrasena para entrar a `/panel` | no |
| `PANEL_SECRET` | `openssl rand -hex 32` | no |

Las cuatro de abajo **no** llevan `NEXT_PUBLIC_` a proposito: se leen solo en el
servidor. Es lo que permite que el panel use una clave admin sin exponerla.

> **Las dos `NEXT_PUBLIC_*` se incrustan en el build, no se leen en runtime.**
> Consecuencia practica: **si las cambias, hay que redesplegar el servicio
> Web**, no alcanza con reiniciarlo. Las otras cuatro si se leen en runtime.

> **AVISO SOBRE LA PAGINA DE DEMO (`/`).** `NEXT_PUBLIC_API_KEY` queda dentro
> del JavaScript que descarga cualquiera que abra la pagina — es publica por
> definicion. Esa pagina usa una clave con scope `tenant`, que **puede subir
> documentos**. Con un tenant de demo el riesgo es acotado; **no la apuntes al
> tenant de un cliente real**. Para clientes reales, emiti desde el panel una
> clave con scope `chat`, que solo puede conversar.

### Panel de administracion

Queda en `https://TU-WEB.up.railway.app/panel`, protegido con `PANEL_PASSWORD`.
Desde ahi se crean clientes, se edita su comportamiento, se suben y borran sus
documentos, se ajusta su tope mensual y se emiten sus claves — sin tocar
`/docs` ni la linea de comandos.

## 4. Primer arranque

Una vez que la API esta verde:

```bash
curl https://TU-API.up.railway.app/health
```

Tiene que devolver `{"status":"ok","environment":"production"}`.

Despues, crear la primera clave admin. Como el comando habla directo con la
base, se corre desde tu maquina apuntando a la base de produccion:

```bash
cd apps/api && DATABASE_URL='<la DATABASE_URL publica de Railway>' uv run python -m app.cli crear-clave-admin --nombre "admin produccion"
```

Guardala en tu gestor de contrasenas: no se vuelve a mostrar.

Con esa clave ya podes crear clientes y subirles documentos desde
`https://TU-API.up.railway.app/docs`.

---

## Pendientes conocidos

Cosas que este despliegue **no** resuelve todavia:

- **Backups de la base.** Railway tiene backups automaticos segun el plan;
  verifica cual te toca. Ahi van a vivir las conversaciones y documentos de
  clientes reales.
- **Alertas de caida.** Si el servicio se cae de madrugada, hoy nadie se entera.
- **WhatsApp.** El envio de mensajes todavia no funciona: falta el access token
  por cliente (ver el `TODO` en `app/channels/whatsapp/client.py`).
- **Rate limit de Voyage.** Con 3 RPM del plan sin medio de pago, dos clientes
  conversando a la vez ya lo agotan.
