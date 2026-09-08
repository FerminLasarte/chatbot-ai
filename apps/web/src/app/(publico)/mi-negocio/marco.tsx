import { Navegacion, type Seccion } from "@/components/navegacion";
import { InterruptorDeTema } from "@/components/tema";

// El marco del portal: lo que rodea a las dos pantallas del duenio.
//
// ★ POR QUE SALIO DE page.tsx
// Mientras el portal era una sola pantalla, el encabezado y el "no puedo
// dejarte pasar" vivian adentro de ella y estaba bien. Con la ficha son dos, y
// dejarlos ahi obligaba a la segunda a importar de la primera -o, peor, a
// copiarlos-. El dia que cambie el encabezado tiene que cambiar en las dos.

const SECCIONES = [
  { href: "/mi-negocio", etiqueta: "Conversaciones" },
  { href: "/mi-negocio/datos", etiqueta: "Mi negocio" },
] as const;

export function Marco({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 px-4 py-10 sm:py-14">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">{children}</div>
    </div>
  );
}

/**
 * Pantalla de "no puedo dejarte pasar", redactada para alguien no tecnico.
 *
 * ★ No explica el error: dice que hacer. A quien abre un link vencido no le
 * sirve saber que su clave fue revocada; le sirve saber a quien pedirle otro.
 */
export function SinAcceso({ titulo, detalle }: { titulo: string; detalle: string }) {
  return (
    <Marco>
      <section className="rounded-panel border border-borde bg-superficie p-6 shadow-panel sm:p-8">
        <h1 className="font-titulo text-xl font-semibold tracking-tight text-texto">{titulo}</h1>
        <p className="mt-2 text-sm text-texto-suave">{detalle}</p>
      </section>
    </Marco>
  );
}

/**
 * El encabezado del portal: de quien es, como viene, y las dos secciones.
 *
 * `estado` es la linea de abajo del nombre. Cambia por pantalla porque lo que
 * hace falta saber cambia: en Conversaciones, si alguien esta esperando; en la
 * ficha, para que sirve lo que se esta por editar.
 */
export function EncabezadoDelPortal({
  nombre,
  estado,
  esperando,
}: {
  nombre: string;
  estado: React.ReactNode;
  /** Cuantas conversaciones piden una persona. Va como contador en el nav para
   *  que se vea desde la ficha: es lo unico que puede estar esperando mientras
   *  alguien edita sus horarios. */
  esperando?: number;
}) {
  const secciones: Seccion[] = SECCIONES.map(({ href, etiqueta }) => ({
    href,
    etiqueta,
    cuantos: href === "/mi-negocio" ? esperando : undefined,
  }));

  return (
    <header className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-titulo text-3xl font-semibold tracking-tight text-texto">
            {nombre}
          </h1>
          <p className="mt-1 text-sm text-texto-suave">{estado}</p>
        </div>
        <InterruptorDeTema />
      </div>

      <Navegacion secciones={secciones} className="lg:flex-row" />
    </header>
  );
}
