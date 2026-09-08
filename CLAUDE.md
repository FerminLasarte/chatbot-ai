# Como se trabaja en este repo

Reglas de trabajo para cualquiera que toque este codigo —persona o agente—.
Lo que explica **por que** el sistema es como es vive en
[docs/architecture.md](docs/architecture.md); lo que explica **como se ve** vive
en [docs/design.md](docs/design.md). Aca esta solo lo que hay que respetar al
escribir.

## 1. Codigo prolijo y modularizado

**Un archivo, una responsabilidad.** Nada de pantallas de 400 lineas donde
conviven datos, layout y formularios, ni servicios que hacen tres cosas. Si un
archivo crecio de mas mientras lo tocabas, partirlo es parte del trabajo, no una
tarea aparte.

**Antes de escribir algo, fijarse si ya existe.** En el frontend, mirar
`apps/web/src/components/` y `apps/web/src/lib/`. En el backend, mirar
`app/services/` antes de escribir una consulta nueva en una ruta.

**Al terminar una tanda, revisar hacia atras.** Si algo quedo duplicado o un
archivo quedo demasiado grande, decirlo aunque no lo hayan pedido. Dejar la zona
que se toco mejor que como estaba.

## 2. Que se comparte y que no

El error a evitar es **el mismo componente escrito de dos formas distintas en
dos lugares**. Ya paso una vez con los estilos copiados a mano entre pantallas,
y el resultado fue que el mismo boton tenia dos grises.

La regla que resuelve los dos lados:

- **Se comparte la APARIENCIA y la forma de los datos.** Como se ve un boton,
  como se ve una tarjeta, como se dibuja una lista de conversaciones, como se
  dibuja la ficha del negocio. Eso vive en `apps/web/src/components/`.
- **No se fusionan contratos que no son el mismo.** El panel de la agencia y el
  portal del cliente tienen credenciales, tipos de estado y Server Actions
  propias, y esa frontera es deliberada: es lo que hace dificil que un cambio en
  el panel filtre algo hacia la pagina que abre el cliente final.

En la practica: los componentes compartidos son **presentacionales** y reciben
por props lo que cambia entre los dos lados (la accion de servidor, las
etiquetas). Cada lado pone su propio `Formulario` con su propio `useActionState`.
Ver `components/conversaciones.tsx` y `components/hilo.tsx`, que ya lo hacen.

En el backend vale lo mismo: cuando dos rutas con autenticaciones distintas
hacen la misma operacion, la operacion vive en `app/services/` y las rutas solo
resuelven quien esta preguntando. Ver `services/conversaciones.py`.

## 3. Comentarios

El repo comenta el **por que**, no el que. Un comentario que repite lo que dice
la linea de abajo sobra; uno que explica una decision no obvia —o una trampa que
costo dias— vale mas que el codigo que acompania. Las trampas criticas van
marcadas con `★` para poder encontrarlas.

Los comentarios y los docs se escriben **sin acentos** (el codigo del repo es
consistente en eso). Los textos que ve el usuario en pantalla, **con acentos**.

## 4. La base nunca se toca a mano

Todo cambio de esquema pasa por una migracion de Alembic versionada y
commiteada, y hay que **leer** lo que genera `--autogenerate`: no detecta
renombres (los ve como drop + create, lo que borra datos) ni algunos indices.
Detalle en el [README](README.md#migraciones-alembic).

## 5. Tests

Un test por cada cosa que puede fallar **en silencio**. Ese es el criterio: si
romperlo produce un error visible, el test es opcional; si romperlo deja al bot
mudo o le muestra a un cliente los datos de otro, el test no es negociable.

Los que ya existen y no se tocan sin entender por que estan:
`test_tenant_isolation.py`, `test_quota.py`, `test_webhook_idempotencia.py`,
`test_coexistence.py`.

Antes de dar algo por terminado:

```bash
cd apps/api && uv run ruff check . && uv run mypy app && uv run pytest
```

## 6. Secretos

Nunca commitear `.env`. Ninguna clave viaja en una URL ni en un query param
(quedan en los logs de acceso). Las claves de API se guardan hasheadas y el
secreto se muestra una sola vez. `ADMIN_API_KEY` **no** lleva el prefijo
`NEXT_PUBLIC_`: con el, Next la incrusta en el bundle del navegador.

## 7. Git

Commits en castellano, con prefijo (`feat:`, `fix:`, `docs:`, `refactor:`) y
explicando el por que en el cuerpo cuando no es obvio.

**El push lo hace Fermin.** Dejar el commit local y avisar que queda listo para
subir: Railway despliega solo al recibir el push en `main`.
