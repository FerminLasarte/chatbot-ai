# Diseno del producto

Como se ve y como se siente todo lo que el usuario abre: el panel de la agencia
(`/panel`), el portal del cliente (`/mi-negocio`) y el alta (`/onboarding`).

Esto no es decoracion. El producto se le vende a PyMEs y lo usa gente no
tecnica: el panel es la cara visible del servicio.

## La estetica: Apple + Notion

- **De Apple**: calma tipografica, espacio en blanco, jerarquia clara,
  movimientos discretos. Nada parpadea ni salta.
- **De Notion**: densidad informativa sin ruido, todo en bloques, y la sensacion
  de que lo que ves se puede editar ahi mismo.
- **Minimalista e intuitivo.** Si un elemento no ayuda a decidir algo, sobra.

**Cada componente se ubica por como se usa, no por donde entra.** Lo que alguien
mira todos los dias va primero; lo que se toca una vez por cliente, despues. Lo
que pide una accion —una conversacion esperando— va arriba de todo y con color.
Nada de volcar campos en una columna porque si.

Cuando haya varias formas razonables de mostrar algo, **mostrar las opciones
antes de elegir**.

## Los tokens: `apps/web/src/app/globals.css`

Ninguna pantalla escribe un color a mano. Se usan los tokens, que le ponen
nombre a la **intencion**:

| Token | Para que |
| --- | --- |
| `fondo`, `superficie`, `superficie-2` | superficies, de atras hacia adelante |
| `borde`, `borde-fuerte` | separaciones |
| `texto`, `texto-suave`, `texto-tenue` | el contenido, lo que acompania, lo accesorio |
| `acento`, `acento-fuerte`, `acento-suave` | **solo lo que se puede tocar** |
| `alerta` / `alerta-suave` | "esto pide que alguien haga algo" |
| `error` / `error-suave` | "algo salio mal" |
| `ok` / `ok-suave` | "salio bien" |

Dos reglas que se siguen de ahi:

1. **El acento es escaso a proposito.** Una sola cosa por pantalla merece ser el
   boton principal. Repartido, deja de ser lo que el ojo encuentra primero.
2. **`alerta` y `error` no son lo mismo.** Una derivacion esperando es `alerta`;
   una llamada que fallo es `error`. Mezclarlos hace que el naranja deje de
   significar "alguien esta esperando".

El modo oscuro se resuelve una sola vez, en los tokens. Nunca con un `dark:`
pegado a cada clase.

En pantallas grandes sube el `font-size` del documento (17 px desde 1536 px,
18 px desde 1920 px). Como Tailwind mide en rem, eso agranda texto, padding y
separaciones **en proporcion**, sin tocar ninguna pantalla.

## Los ladrillos: `apps/web/src/components/ui.tsx`

| Pieza | Que es |
| --- | --- |
| `claseBoton(variante)` | como se ve un boton: `principal`, `suave`, `peligro` |
| `claseCampo` / `claseCampoAngosto` | como se ve un campo |
| `Tarjeta` | el bloque blanco sobre el que se apoya todo |
| `Bloque` | tarjeta con titulo y una linea de ayuda **arriba**, no abajo |
| `Chip` | etiqueta chica de estado (`neutro`, `alerta`, `ok`, `acento`) |
| `Aviso` | el resultado de una accion |
| `Vacio` | que decir cuando una lista no tiene nada |

**No tienen `"use client"` a proposito**: los usan paginas de servidor, y un
modulo marcado como cliente exporta referencias, no valores —interpolar una en
un template string deja el `className` en basura sin que TypeScript diga nada—.

## Componentes compartidos entre el panel y el portal

Viven en `components/` y son **presentacionales**: reciben por props lo que
cambia entre los dos lados (la accion de servidor con su credencial, como se
llama a quien contesto a mano, que acciones van al pie). Hoy:

- `conversaciones.tsx` — la lista, con las que esperan primero.
- `hilo.tsx` — el hilo y la atribucion de cada mensaje.
- `panel-lateral.tsx` — el panel que se abre al costado.

Lo que **no** se comparte es el tipo de estado de cada lado ni sus Server
Actions: `app/panel/ui.tsx` y `app/mi-negocio/ui.tsx` tienen cada uno su
`Formulario` con su `useActionState`. Ver la regla completa en
[CLAUDE.md](../CLAUDE.md#2-que-se-comparte-y-que-no).

## Escribir para el que lee

Dos publicos distintos y **el mismo tono claro para los dos**: frases cortas,
sin jerga, y diciendo que hacer.

- En el **portal** escribe alguien que no sabe que es un token ni un webhook.
  Un error no se explica: se dice que hacer ("pedile el link actualizado a quien
  te lo paso").
- En el **panel** se puede ser tecnico, pero no criptico: "Pidieron una
  persona · hace 3 h" le sirve a alguien apurado; "escalated_at" no.

Los estados vacios dicen que va a pasar cuando haya algo, no "sin datos".

## Fechas y horas: las calcula la API

El panel se renderiza en el servidor (Railway, en UTC). Si comparara fechas por
su cuenta mostraria horas que no son las de quien mira. La API manda **numeros
ya resueltos** (`minutos_inactiva`, `minutos_restantes`) y el frontend los
formatea con `lib/duracion.ts`: "hace 5 min", "vuelve en 2 h".

Ademas, leer el reloj durante el render rompe la regla de pureza de React.

## Checklist antes de dar una pantalla por terminada

- [ ] Ningun color escrito a mano; todo sale de los tokens.
- [ ] Lo que se usa todos los dias esta arriba; lo que pide accion, resaltado.
- [ ] Un solo boton principal.
- [ ] Estado vacio, estado cargando y estado de error, los tres.
- [ ] Se lee bien en un celular y en un monitor de 27 pulgadas.
- [ ] El foco por teclado se ve (lo da `:focus-visible` global, no romperlo).
- [ ] Modo oscuro correcto sin haber escrito un solo `dark:`.
- [ ] Nada que ya exista en `components/` fue reescrito al lado.
