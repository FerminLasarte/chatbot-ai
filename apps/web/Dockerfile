# Imagen de produccion del frontend.
#
# OJO CON LAS VARIABLES NEXT_PUBLIC_*: Next las incrusta en el bundle de
# JavaScript durante el BUILD, no las lee en runtime. Por eso van como ARG y
# hay que pasarlas en el `docker build`; definirlas solo en el hosting como
# variables de entorno del contenedor NO tiene efecto -la app se construye con
# el valor vacio y falla en el navegador.

FROM node:22-slim AS builder

WORKDIR /app

# npm ci con el lockfile: las mismas versiones que en local y en CI.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Se incrustan en el bundle durante el build (ver nota de arriba).
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_API_KEY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_API_KEY=$NEXT_PUBLIC_API_KEY

RUN npm run build


FROM node:22-slim AS runtime

# La imagen de node ya trae el usuario `node` (uid 1000) sin privilegios: se
# reusa en vez de crear otro. Si alguien logra ejecutar codigo dentro del
# contenedor, no lo hace como root.
WORKDIR /app

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0

# `standalone` deja en .next/standalone un server.js con solo lo necesario.
# static/ y public/ van aparte: el server standalone no los incluye.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node

EXPOSE 3000

CMD ["sh", "-c", "PORT=${PORT:-3000} node server.js"]
