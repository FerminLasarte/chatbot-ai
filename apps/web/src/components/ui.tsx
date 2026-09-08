// Los ladrillos visuales del producto. Sin estado, sin hooks, sin "use client".
//
// ★ QUE SE COMPARTE Y QUE NO
// El panel de la agencia y el portal del cliente mantienen cada uno su propio
// formulario y su propio tipo de estado, y esa frontera es a proposito (ver la
// nota en app/(panel)/panel/ui.tsx). Lo que NO tiene sentido duplicar es como
// se ve un boton: la version copiada ya habia divergido de la original. Aca
// vive la APARIENCIA; el comportamiento sigue de cada lado.
//
// ★ POR QUE ESTOS COMPONENTES SIRVEN PARA LAS DOS PIELES
// Ninguna clase de este archivo nombra un color ni una medida: dice
// `bg-acento`, `rounded-control`, `py-fila`. Que el acento sea petroleo o
// verde tinta, y que una fila mida 11 px o 15 px, lo decide la piel en la que
// esta montado el componente (ver globals.css). Por eso el panel es denso y el
// portal respira sin que exista una sola condicion en este archivo.
//
// ★ SIN "use client" A PROPOSITO
// Estos componentes los usan paginas de servidor. Un modulo marcado con
// "use client" exporta referencias, no valores: interpolarlas en un template
// string deja el className en basura sin que TypeScript diga nada.

/* ---------------------------------------------------------------------------
 * Botones
 * ------------------------------------------------------------------------ */

type Variante = "principal" | "suave" | "fantasma" | "peligro";
type Tamanio = "normal" | "chico";

const POR_VARIANTE: Record<Variante, string> = {
  // Una sola cosa por pantalla merece ser el boton principal: el acento es lo
  // que el ojo encuentra primero y pierde sentido si se reparte.
  //
  // `text-sobre-acento` y no `text-white`: en modo oscuro el acento se aclara,
  // y un blanco fijo dejaria letras blancas sobre un fondo claro.
  principal:
    "bg-acento text-sobre-acento shadow-panel hover:bg-acento-fuerte active:translate-y-px",
  suave:
    "border border-borde-fuerte bg-superficie text-texto hover:bg-superficie-2 active:translate-y-px",
  fantasma: "text-texto-suave hover:bg-superficie-2 hover:text-texto",
  peligro: "border border-borde text-error hover:bg-error-suave hover:border-error",
};

const POR_TAMANIO: Record<Tamanio, string> = {
  normal: "px-3.5 py-2 text-sm",
  chico: "px-2.5 py-1.5 text-xs",
};

/** Clases de un boton. Suelta, para los `<button>` que ya viven en un cliente. */
export function claseBoton(variante: Variante = "principal", tamanio: Tamanio = "normal"): string {
  return (
    "inline-flex items-center justify-center gap-1.5 rounded-control font-medium " +
    "whitespace-nowrap transition-[background-color,border-color,color,transform] " +
    "duration-100 disabled:pointer-events-none disabled:opacity-40 " +
    POR_TAMANIO[tamanio] +
    " " +
    POR_VARIANTE[variante]
  );
}

/* ---------------------------------------------------------------------------
 * Campos
 * ------------------------------------------------------------------------ */

/** Un campo de texto. */
export const claseCampo =
  "w-full rounded-control border border-borde bg-superficie px-3 py-2 text-sm text-texto " +
  "transition-colors placeholder:text-texto-tenue hover:border-borde-fuerte " +
  "focus:border-acento focus:outline-none";

/** La variante angosta: mide lo que mide su contenido (un desplegable de horas).
 *
 *  No alcanza con agregarle `w-auto` al de arriba: Tailwind resuelve el empate
 *  entre dos utilidades de ancho por el orden en la hoja, no en el atributo. */
export const claseCampoAngosto = claseCampo.replace("w-full ", "");

/** La etiqueta de un campo. Va ARRIBA del campo, siempre visible: un
 *  placeholder que hace de etiqueta desaparece justo cuando alguien esta
 *  escribiendo y necesita confirmar que esta llenando lo que cree. */
export function Etiqueta({
  children,
  ayuda,
}: {
  children: React.ReactNode;
  /** Para que sirve el campo, en pocas palabras. */
  ayuda?: string;
}) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className="text-xs font-medium text-texto">{children}</span>
      {ayuda && <span className="text-xs text-texto-suave">{ayuda}</span>}
    </span>
  );
}

/* ---------------------------------------------------------------------------
 * Superficies
 * ------------------------------------------------------------------------ */

/** Una tarjeta: el bloque sobre el que se apoya todo. */
export function Tarjeta({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-panel border border-borde bg-superficie shadow-panel ${className}`}
    >
      {children}
    </section>
  );
}

/** Tarjeta con titulo y una linea de ayuda. */
export function Bloque({
  titulo,
  ayuda,
  acciones,
  pie,
  children,
  className = "",
  /** Sin padding interno: para cuando adentro va una lista que llega hasta el
   *  borde. Una lista con margen adentro de una tarjeta con margen se lee como
   *  dos cajas, no como una. */
  alBorde = false,
}: {
  titulo: string;
  /** Para que sirve esto, en una linea. Va arriba y no abajo: se lee antes de
   *  intentar usar la seccion, no despues de haberse equivocado. */
  ayuda?: string;
  /** Lo que se puede hacer con la seccion entera, alineado al titulo. */
  acciones?: React.ReactNode;
  pie?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  alBorde?: boolean;
}) {
  return (
    <Tarjeta className={`overflow-hidden ${className}`}>
      <header className="flex items-start justify-between gap-4 border-b border-borde px-4 py-3">
        <div className="min-w-0">
          <h2 className="font-titulo text-sm font-semibold tracking-tight text-texto">
            {titulo}
          </h2>
          {ayuda && <p className="mt-0.5 text-xs text-texto-suave">{ayuda}</p>}
        </div>
        {acciones && <div className="shrink-0">{acciones}</div>}
      </header>

      <div className={alBorde ? "" : "px-4 py-3.5"}>{children}</div>

      {pie && <footer className="border-t border-borde px-4 py-3">{pie}</footer>}
    </Tarjeta>
  );
}

/** El encabezado de una pantalla: de que es, y la accion principal. */
export function Encabezado({
  titulo,
  detalle,
  acciones,
}: {
  titulo: string;
  /** Una linea que diga como viene la cosa, no que es la pantalla. */
  detalle?: React.ReactNode;
  acciones?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="font-titulo text-2xl font-semibold tracking-tight text-texto">
          {titulo}
        </h1>
        {detalle && <p className="mt-0.5 text-sm text-texto-suave">{detalle}</p>}
      </div>
      {acciones && <div className="flex shrink-0 items-center gap-2">{acciones}</div>}
    </header>
  );
}

/* ---------------------------------------------------------------------------
 * Estado
 * ------------------------------------------------------------------------ */

type Tono = "neutro" | "alerta" | "ok" | "error" | "acento";

const POR_TONO: Record<Tono, string> = {
  neutro: "bg-superficie-2 text-texto-suave",
  alerta: "bg-alerta-suave text-alerta",
  ok: "bg-ok-suave text-ok",
  error: "bg-error-suave text-error",
  acento: "bg-acento-suave text-acento-fuerte",
};

/** Una etiqueta chica de estado. `alerta` es la que pide una accion. */
export function Chip({
  tono = "neutro",
  children,
}: {
  tono?: Tono;
  children: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ${POR_TONO[tono]}`}
    >
      {/* El punto solo en los dos tonos que significan "esto no esta resuelto".
          En un chip neutro seria decoracion. */}
      {(tono === "alerta" || tono === "error") && (
        <span className="size-1.5 rounded-full bg-current" />
      )}
      {children}
    </span>
  );
}

/**
 * El resultado de una accion: lo que salio bien o lo que fallo.
 *
 * Recibe dos strings sueltos y no el `Estado` de cada lado a proposito: asi el
 * portal no tiene que importar tipos del panel para verse igual.
 */
export function Aviso({
  error,
  ok,
  className = "",
}: {
  error?: string;
  ok?: string;
  className?: string;
}) {
  if (!error && !ok) return null;
  return (
    <p
      role="status"
      className={`rounded-control px-3 py-2 text-sm ${
        error ? "bg-error-suave text-error" : "bg-ok-suave text-ok"
      } ${className}`}
    >
      {error ?? ok}
    </p>
  );
}

/**
 * Lo que se muestra cuando una lista todavia no tiene nada.
 *
 * ★ Dice que va a pasar cuando haya algo, no "sin datos". Quien abre una
 * pantalla vacia por primera vez necesita saber si esta rota o si todavia no
 * paso nada.
 */
export function Vacio({
  titulo,
  children,
  accion,
}: {
  titulo: string;
  /** Que va a hacer que esto deje de estar vacio. */
  children?: React.ReactNode;
  accion?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
      <p className="font-titulo text-sm font-semibold text-texto">{titulo}</p>
      {children && <p className="max-w-sm text-sm text-texto-suave">{children}</p>}
      {accion && <div className="mt-2">{accion}</div>}
    </div>
  );
}

/** El esqueleto de algo que esta cargando: la forma, sin contenido inventado. */
export function Esqueleto({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-control bg-superficie-2 ${className}`}
    />
  );
}
