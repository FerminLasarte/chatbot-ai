import Link from "next/link";

import { InterruptorDeTema } from "@/components/tema";
import { salir } from "./acciones";

// El marco del panel: la barra de arriba y el ancho del contenido.
//
// ★ POR QUE NO ES UN layout.tsx
// Un layout envolveria tambien a /panel/login, y la barra ahi no tiene sentido:
// muestra "Salir" y el nombre de quien entro cuando todavia no entro nadie. Las
// dos pantallas que si estan adentro la piden explicitamente, que ademas hace
// evidente donde empieza la parte con sesion.

export function BarraDelPanel({ children }: { children?: React.ReactNode }) {
  return (
    // `sticky` y no `fixed`: asi la barra sigue ocupando su lugar en el flujo y
    // el contenido no queda tapado sin que nadie le ponga un padding a mano.
    <header className="sticky top-0 z-30 border-b border-borde bg-superficie/85 backdrop-blur-md">
      <div className="flex h-12 items-center gap-4 px-4 lg:px-6">
        <Link
          href="/panel"
          className="flex items-baseline gap-2 rounded-control text-sm font-semibold tracking-tight text-texto"
        >
          ArgencoreAI
          <span className="text-[11px] font-normal text-texto-tenue">Panel</span>
        </Link>

        {/* Lo que cambia por pantalla: las migas, el nombre del cliente. */}
        <div className="min-w-0 flex-1">{children}</div>

        <div className="flex shrink-0 items-center gap-2">
          <InterruptorDeTema />
          <form action={salir}>
            <button
              type="submit"
              className="rounded-control px-2.5 py-1.5 text-xs text-texto-suave transition-colors hover:bg-superficie-2 hover:text-texto"
            >
              Salir
            </button>
          </form>
        </div>
      </div>
    </header>
  );
}

/** El ancho del contenido del panel.
 *
 *  ★ Ancho de verdad y no una columna angosta centrada: esto se mira en un
 *  monitor grande y todo el dia. Con el contenido encerrado en 42rem, dos
 *  tercios de la pantalla quedaban en blanco y una lista de veinte
 *  conversaciones obligaba a scrollear sin necesidad. El tope existe igual
 *  porque una fila de 2500 px de ancho tampoco se lee. */
export function AnchoDelPanel({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex-1 px-4 py-6 lg:px-6 lg:py-8">
      <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6">{children}</div>
    </main>
  );
}
