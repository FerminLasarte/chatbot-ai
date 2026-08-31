// Los ladrillos visuales del producto. Sin estado, sin hooks, sin "use client".
//
// ★ QUE SE COMPARTE Y QUE NO
// El panel de la agencia y el portal del cliente mantienen cada uno su propio
// formulario y su propio tipo de estado, y esa frontera es a proposito (ver la
// nota en panel/ui.tsx). Lo que NO tiene sentido duplicar es como se ve un
// boton: la version copiada ya habia divergido de la original. Aca vive la
// APARIENCIA; el comportamiento sigue de cada lado.
//
// ★ SIN "use client" A PROPOSITO
// Estos componentes los usan paginas de servidor. Un modulo marcado con
// "use client" exporta referencias, no valores: interpolarlas en un template
// string deja el className en basura sin que TypeScript diga nada (ver la nota
// larga en lib/estilos.ts).

type Variante = "principal" | "suave" | "peligro";

/** Clases de un boton. Suelta, para los `<button>` que ya viven en un cliente. */
export function claseBoton(variante: Variante = "principal"): string {
  const porVariante: Record<Variante, string> = {
    // Una sola cosa por pantalla merece ser el boton principal: el acento es lo
    // que el ojo encuentra primero y pierde sentido si se reparte.
    principal: "bg-acento text-white hover:bg-acento-fuerte",
    suave: "border border-borde-fuerte text-texto hover:bg-superficie-2",
    peligro: "border border-borde text-error hover:bg-error-suave",
  };
  return (
    "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm " +
    "font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 " +
    porVariante[variante]
  );
}

/** Un campo de texto. */
export const claseCampo =
  "w-full rounded-lg border border-borde bg-superficie px-3 py-2 text-sm text-texto " +
  "placeholder:text-texto-tenue focus:border-acento focus:outline-none";

/** La variante angosta: mide lo que mide su contenido (un desplegable de horas).
 *
 *  No alcanza con agregarle `w-auto` al de arriba: Tailwind resuelve el empate
 *  entre dos utilidades de ancho por el orden en la hoja, no en el atributo. */
export const claseCampoAngosto = claseCampo.replace("w-full ", "");

/** Una tarjeta: el bloque blanco sobre el que se apoya todo. */
export function Tarjeta({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-borde bg-superficie ${className}`}
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
  children,
}: {
  titulo: string;
  /** Para que sirve esto, en una linea. Va arriba y no abajo: se lee antes de
   *  intentar usar la seccion, no despues de haberse equivocado. */
  ayuda?: string;
  /** Lo que se puede hacer con la seccion entera, alineado al titulo. */
  acciones?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Tarjeta>
      <header className="flex items-start justify-between gap-4 border-b border-borde px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-texto">{titulo}</h2>
          {ayuda && <p className="mt-1 text-xs text-texto-suave">{ayuda}</p>}
        </div>
        {acciones}
      </header>
      <div className="px-5 py-4">{children}</div>
    </Tarjeta>
  );
}

/** Una etiqueta chica de estado. `alerta` es la que pide una accion. */
export function Chip({
  tono = "neutro",
  children,
}: {
  tono?: "neutro" | "alerta" | "ok" | "acento";
  children: React.ReactNode;
}) {
  const porTono = {
    neutro: "bg-superficie-2 text-texto-suave",
    alerta: "bg-alerta-suave text-alerta",
    ok: "bg-ok-suave text-ok",
    acento: "bg-acento-suave text-acento-fuerte",
  }[tono];

  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ${porTono}`}
    >
      {tono === "alerta" && <span className="size-1.5 rounded-full bg-alerta" />}
      {children}
    </span>
  );
}

/** El resultado de una accion: lo que salio bien o lo que fallo.
 *
 *  Recibe dos strings sueltos y no el `Estado` de cada lado a proposito: asi el
 *  portal no tiene que importar tipos del panel para verse igual. */
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
      className={`rounded-lg px-3 py-2 text-sm ${
        error ? "bg-error-suave text-error" : "bg-ok-suave text-ok"
      } ${className}`}
    >
      {error ?? ok}
    </p>
  );
}

/** Lo que se muestra cuando una lista todavia no tiene nada. */
export function Vacio({ children }: { children: React.ReactNode }) {
  return <p className="py-2 text-sm text-texto-suave">{children}</p>;
}
