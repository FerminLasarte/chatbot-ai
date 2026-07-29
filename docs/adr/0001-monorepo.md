# ADR 0001 — Monorepo para backend y frontend

- **Fecha:** 2026-07-29
- **Estado:** Aceptado

## Contexto

El producto tiene dos aplicaciones: una API en Python (FastAPI) que contiene el
motor de IA, y una app en Next.js que sirve la landing de la agencia y el dashboard
de gestion de clientes. El equipo es de 1 a 3 personas.

## Decision

Un unico repositorio con las dos apps bajo `apps/`, con un solo `.gitignore` en la
raiz. Sin Turborepo ni Nx.

## Razones

- Los contratos de la API (schemas Pydantic -> tipos TypeScript) y los payloads de
  webhook viven en un solo lugar: un cambio de schema se ve en el mismo PR que
  rompe el dashboard.
- Un solo `docker compose up` levanta el entorno de desarrollo completo.
- Onboarding de un dev nuevo: un `git clone`.
- Turborepo/Nx sirven para compartir paquetes JS entre varias apps JS. Aca el
  backend es Python, asi que no aportan nada y suman configuracion.
- Un unico `.gitignore` en la raiz. Multiples `.gitignore` anidados son la via mas
  comun para que se escape un `.env`.

## Cuando revisar esta decision

- Cuando haya equipos distintos tocando backend y frontend.
- Cuando los ciclos de release sean realmente independientes.
- Cuando aparezca una segunda app Next.js que comparta paquetes con la primera
  (ahi si entra Turborepo).
