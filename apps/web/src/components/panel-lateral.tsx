"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Un panel que entra desde la derecha, sin saber que va adentro.
//
// ★ ESTA SEPARADO DEL HILO A PROPOSITO
// La primera version tenia el comportamiento del panel -velo, animacion,
// Escape, foco, bloqueo del scroll de atras- mezclado con el dibujo de los
// mensajes. Son dos cosas distintas: lo de abajo vale para cualquier detalle
// que se abra al costado, y en el panel de la agencia va a haber varios. Lo
// unico que sabe este archivo es como se comporta un panel.
//
// POR QUE UN PANEL Y NO UNA PAGINA
// Quien mira una lista casi siempre esta comparando: "de estas cinco, cual es
// la que salio mal". Una pagina aparte obliga a ir y volver, y en cada vuelta
// hay que reencontrar donde estaba. En un telefono no hay lista que preservar,
// asi que ocupa toda la pantalla.

export function PanelLateral({
  abierto,
  titulo,
  subtitulo,
  alCerrar,
  pie,
  children,
}: {
  abierto: boolean;
  /** De que es este panel. Queda fijo arriba mientras el contenido scrollea. */
  titulo: string;
  subtitulo?: string;
  alCerrar: () => void;
  /** Las acciones, al pie y siempre a la vista. */
  pie?: React.ReactNode;
  children: React.ReactNode;
}) {
  // Separado de `abierto` a proposito: la animacion de entrada necesita un
  // frame con el panel ya montado pero todavia corrido.
  const [entrando, setEntrando] = useState(false);
  const velo = useRef<HTMLDivElement>(null);
  const botonCerrar = useRef<HTMLButtonElement>(null);

  const cerrar = useCallback(() => {
    setEntrando(false);
    alCerrar();
  }, [alCerrar]);

  // Escape cierra, y mientras el panel esta abierto la pagina de atras no
  // scrollea: sin esto, en el telefono el dedo mueve la lista en vez del panel.
  useEffect(() => {
    if (!abierto) return;

    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") cerrar();
    };
    window.addEventListener("keydown", alTeclear);

    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const id = window.setTimeout(() => {
      setEntrando(true);
      botonCerrar.current?.focus();
    }, 10);

    return () => {
      window.removeEventListener("keydown", alTeclear);
      document.body.style.overflow = overflow;
      clearTimeout(id);
    };
  }, [abierto, cerrar]);

  if (!abierto) return null;

  return (
    <div className="fixed inset-0 z-50">
      {/* ★ El velo es HERMANO del panel, no su padre. Anidado, su backdrop-blur
          alcanza tambien al contenido y todo se lee borroso: backdrop-filter
          afecta a lo que se pinta encima dentro de su contexto. */}
      <div
        ref={velo}
        onClick={cerrar}
        className={`absolute inset-0 bg-black/20 backdrop-blur-[2px] transition-opacity duration-200 motion-reduce:transition-none ${
          entrando ? "opacity-100" : "opacity-0"
        }`}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className={`absolute inset-y-0 right-0 flex w-full flex-col border-borde bg-superficie shadow-2xl transition-transform duration-200 ease-out motion-reduce:transition-none sm:max-w-md sm:border-l ${
          entrando ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-borde px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-medium text-texto">{titulo}</h2>
            {subtitulo && <p className="mt-0.5 text-xs text-texto-suave">{subtitulo}</p>}
          </div>
          <button
            ref={botonCerrar}
            type="button"
            onClick={cerrar}
            aria-label="Cerrar"
            className="-mt-1 -mr-2 rounded-lg px-2 py-1 text-lg leading-none text-texto-tenue transition-colors hover:bg-superficie-2 hover:text-texto"
          >
            &times;
          </button>
        </header>

        {children}

        {pie && <footer className="border-t border-borde px-5 py-4">{pie}</footer>}
      </aside>
    </div>
  );
}
