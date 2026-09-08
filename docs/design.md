# Diseno del producto

Como se ve y como se siente todo lo que el usuario abre: el panel de la agencia
(`/panel`), el portal del cliente (`/mi-negocio`) y el alta (`/onboarding`).

Esto no es decoracion. El producto se le vende a PyMEs y lo usa gente no
tecnica: el panel es la cara visible del servicio.

## Dos pieles, un solo sistema

**El cliente nunca ve el panel.** Eso, que parece un detalle, es la decision de
diseno mas importante que hay tomada: no existe ninguna coherencia de marca que
proteger entre el panel de la agencia y las pantallas que abre el comercio. Son
dos herramientas, para dos personas, con dos trabajos distintos.

| Piel | Donde | Como es | Por que |
| --- | --- | --- | --- |
| `consola` | `/panel` | Grises frios, acento petroleo, filas cortas, numeros en monoespaciada tabular | Se mira ocho horas en un monitor grande. Densidad alta: la misma lista entra con varias filas mas |
| `papel` | `/`, `/mi-negocio`, `/onboarding`, legales | Papel hueso, verde tinta, aire, titulos en Fraunces | Lo abre desde el celular alguien que no es tecnico, una vez por semana. Es lo que vende el servicio |

**El acento de `papel` sale del mundo donde vive el producto** —el verde de
WhatsApp, bajado a algo que se pueda mirar todo el dia sin que grite—. El de
`consola` es petroleo y deliberadamente **no** es azul: el azul generico es
exactamente lo que hace que un panel parezca una plantilla.

### La regla que hace que esto no cueste dos librerias

**Cambian los VALORES, nunca los NOMBRES.** `--acento` significa "esto se puede
tocar" en las dos pieles; solo difiere en que color es. `--fila-y` es "la altura
de una fila" en las dos; solo difiere en cuanto mide.

Por eso `components/ui.tsx` no tiene una sola condicion adentro y el mismo
`<Chip>` se dibuja denso en el panel y con aire en el portal. Y por eso agregar
una tercera piel algun dia es un bloque de variables, no otra libreria.

El error que esto evita es el que ya paso una vez en este repo: **el mismo boton
escrito de dos formas distintas en dos lugares**, con dos grises.

### Como se aplica una piel

`data-piel` es un atributo **estatico del `<html>`**, y por eso hay **dos layouts
raiz**, uno por grupo de rutas (`app/(panel)/layout.tsx` y
`app/(publico)/layout.tsx`). Con un solo layout habria que colgarlo de un `div`
de adentro, y entonces pasarian dos cosas: el fondo del `<body>` quedaria de la
otra piel —se ve al rebotar el scroll— y **cada pantalla del producto
descargaria las cuatro tipografias** en vez de las dos que usa.

Los grupos entre parentesis no aparecen en la URL: `/panel` sigue siendo
`/panel`. El unico costo es que navegar entre el panel y el portal fuerza una
recarga completa, y eso no pasa nunca: son dos credenciales distintas.

## Los tokens: `apps/web/src/app/globals.css`

Ninguna pantalla escribe un color a mano. Se usan los tokens, que le ponen
nombre a la **intencion**:

| Token | Para que |
| --- | --- |
| `fondo`, `superficie`, `superficie-2` | superficies, de atras hacia adelante |
| `borde`, `borde-fuerte` | separaciones |
| `texto`, `texto-suave`, `texto-tenue` | el contenido, lo que acompania, lo accesorio |
| `acento`, `acento-fuerte`, `acento-suave` | **solo lo que se puede tocar** |
| `sobre-acento` | el texto que va **encima** del acento |
| `alerta` / `alerta-suave` | "esto pide que alguien haga algo" |
| `error` / `error-suave` | "algo salio mal" |
| `ok` / `ok-suave` | "salio bien" |
| `fila-y` (`py-fila`) | la densidad de una fila, segun la piel |
| `radio-panel`, `radio-control` | las esquinas, segun la piel |

Tres reglas que se siguen de ahi:

1. **El acento es escaso a proposito.** Una sola cosa por pantalla merece ser el
   boton principal. Repartido, deja de ser lo que el ojo encuentra primero.
2. **`alerta` y `error` no son lo mismo.** Una derivacion esperando es `alerta`;
   una llamada que fallo es `error`. Mezclarlos hace que el naranja deje de
   significar "alguien esta esperando".
3. **Nunca `text-white` sobre `bg-acento`.** Va `text-sobre-acento`: en modo
   oscuro el acento se aclara, y un blanco fijo deja letras blancas sobre un
   fondo claro.

### El modo oscuro: `light-dark()`, no un `@media` por piel

Cada token declara sus dos valores en la misma linea:

```css
--fondo: light-dark(#fbfaf7, #161614);
```

Quien elige cual se usa es `color-scheme`, que ademas le arregla de paso el
color a los scrollbars y a los controles nativos del navegador.

Con dos pieles y tres estados de tema la version con media queries son **seis
bloques de valores** para mantener sincronizados a mano. Asi es **uno por piel**.

### El tema tiene tres estados, no dos

`sistema` (el que viene por defecto, y se representa por **ausencia** del
atributo `data-tema`), `claro` y `oscuro`. Un interruptor de dos posiciones
obliga a elegir en la primera visita y despues no deja volver a "que decida el
sistema", que es la opcion correcta para la mayoria.

El guion que aplica la eleccion guardada corre **antes del primer pintado**
(`lib/tema.ts`). Adentro de un `useEffect`, quien eligio oscuro veria un
fogonazo blanco en cada navegacion.

En pantallas grandes sube el `font-size` del documento (17 px desde 1536 px,
18 px desde 1920 px). Como Tailwind mide en rem, eso agranda texto, padding y
separaciones **en proporcion**, sin tocar ninguna pantalla.

## Los ladrillos: `apps/web/src/components/ui.tsx`

| Pieza | Que es |
| --- | --- |
| `claseBoton(variante, tamanio)` | `principal`, `suave`, `fantasma`, `peligro` |
| `claseCampo` / `claseCampoAngosto` | como se ve un campo |
| `Tarjeta` | el bloque sobre el que se apoya todo |
| `Bloque` | tarjeta con titulo, ayuda **arriba**, acciones y pie |
| `Encabezado` | el titulo de una pantalla y su accion principal |
| `Chip` | etiqueta chica de estado (`neutro`, `alerta`, `ok`, `error`, `acento`) |
| `Aviso` | el resultado de una accion |
| `Vacio` | que decir cuando una lista no tiene nada |
| `Esqueleto` | la forma de algo que esta cargando |

**No tienen `"use client"` a proposito**: los usan paginas de servidor, y un
modulo marcado como cliente exporta referencias, no valores —interpolar una en
un template string deja el `className` en basura sin que TypeScript diga nada—.

Los iconos viven en `components/iconos.tsx`, dibujados a mano: son doce, pesan
menos que el `import` que los buscaria, y asi todos comparten el mismo grosor de
trazo. Todos usan `currentColor`, asi que nunca hay que pasarles un color —y
nunca se puede escribir uno a mano—.

## Componentes compartidos entre el panel y el portal

Viven en `components/` y son **presentacionales**: reciben por props lo que
cambia entre los dos lados (la accion de servidor con su credencial, como se
llama a quien contesto a mano, que acciones van al pie). Hoy:

- `conversaciones.tsx` — la lista, con busqueda y filtros.
- `hilo.tsx` — el hilo, la atribucion de cada mensaje y la caja de respuesta.
- `panel-lateral.tsx` — el panel que se abre al costado.
- `en-vivo.tsx` — el refresco automatico.
- `tema.tsx` — el interruptor de tema.

Lo que **no** se comparte es el tipo de estado de cada lado ni sus Server
Actions: `app/(panel)/panel/ui.tsx` y `app/(publico)/mi-negocio/ui.tsx` tienen
cada uno su `Formulario` con su `useActionState`. Ver la regla completa en
[CLAUDE.md](../CLAUDE.md#2-que-se-comparte-y-que-no).

### Dos fronteras que hay que respetar al tocarlos

1. **Las funciones puras van a `lib/`, no al componente.** `conversaciones.tsx`
   es un componente de **cliente** (filtrar tiene que responder en la tecla), y
   un modulo `"use client"` exporta referencias: una pagina de servidor que
   importara `cuantasEsperan` de ahi recibiria un proxy y explotaria al
   llamarlo. Por eso eso vive en `lib/conversaciones.ts`.

2. **Lo que depende de cada fila viaja YA DIBUJADO.** Las acciones de pausa se
   arman en el servidor y se pasan como JSX, no como una funcion: una funcion no
   cruza la frontera al cliente. El JSX con la Server Action adentro si.

## Que se actualiza solo

`components/en-vivo.tsx` refresca la pantalla cada 20 segundos con
`router.refresh()`, que vuelve a correr el componente de servidor **sin perder
el estado de cliente**: el panel lateral abierto sigue abierto y lo que alguien
estaba escribiendo sigue escrito.

Dos cosas que no se pueden sacar:

- **No refresca con la pestania escondida.** Sin eso, una pestania olvidada en
  el fondo del navegador le pega a la API cada veinte segundos todo el fin de
  semana, y con ella a la base.
- **Al volver a la pestania refresca en el acto.** Quien vuelve despues de un
  rato no tiene por que mirar datos viejos hasta el proximo tic.

Un canal permanente (SSE, websockets) seria otra pieza de infraestructura —y
otra cosa que se puede caer en silencio— para ganar unos segundos que a nadie le
cambian el dia.

## Escribir para el que lee

Dos publicos distintos y **el mismo tono claro para los dos**: frases cortas,
sin jerga, y diciendo que hacer.

- En el **portal** escribe alguien que no sabe que es un token ni un webhook.
  Un error no se explica: se dice que hacer ("pedile el link actualizado a quien
  te lo paso").
- En el **panel** se puede ser tecnico, pero no criptico: "Pidieron una
  persona · hace 3 h" le sirve a alguien apurado; "escalated_at" no.

**La linea debajo de un titulo dice el estado, no que es la pantalla.** Quien
abre `/panel` ya sabe que ahi estan sus clientes; lo que necesita saber es si
hay alguien esperando ahora. Por eso dice "6 negocios · 3 conversaciones esperan
desde hace 3 h" y no "cada cliente tiene su comportamiento y sus documentos".

Los estados vacios dicen que va a pasar cuando haya algo, no "sin datos". Y
**"no hay nada" y "no hay resultados" son dos pantallas distintas**: una se
arregla creando algo y la otra borrando la busqueda.

## Fechas y horas: las calcula la API

El panel se renderiza en el servidor (Railway, en UTC). Si comparara fechas por
su cuenta mostraria horas que no son las de quien mira. La API manda **numeros
ya resueltos** (`minutos_inactiva`, `minutos_restantes`, `minutos_de_ventana`) y
el frontend los formatea con `lib/duracion.ts`: "hace 5 min", "vuelve en 2 h".

Ademas, leer el reloj durante el render rompe la regla de pureza de React.

**La precision baja con la antiguedad.** A los cinco minutos los minutos
importan; a las seis horas "6 h 13 min" es ruido en un chip que se lee de reojo,
y un numero que se mueve solo en una pantalla que se refresca sola.

## Checklist antes de dar una pantalla por terminada

- [ ] Ningun color escrito a mano; todo sale de los tokens.
- [ ] Ningun `text-white` sobre el acento; va `text-sobre-acento`.
- [ ] Se ve bien en las **dos** pieles si el componente es compartido.
- [ ] Lo que se usa todos los dias esta arriba; lo que pide accion, resaltado.
- [ ] Un solo boton principal.
- [ ] Estado vacio, estado cargando y estado de error, los tres. Y "no hay
      nada" distinto de "no hay resultados".
- [ ] Se lee bien en un celular y en un monitor de 27 pulgadas.
- [ ] El foco por teclado se ve (lo da `:focus-visible` global, no romperlo).
- [ ] Modo oscuro correcto sin haber escrito un solo `dark:`, y el interruptor
      manual le gana al sistema operativo en los dos sentidos.
- [ ] Nada que ya exista en `components/` fue reescrito al lado.
