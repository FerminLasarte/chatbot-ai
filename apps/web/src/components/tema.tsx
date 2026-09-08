"use client";

import { useEffect, useState } from "react";

import { IconoLuna, IconoSistema, IconoSol } from "@/components/iconos";
import { CLAVE_TEMA, type Tema } from "@/lib/tema";

// El interruptor de tema. Vive en las dos pieles: el panel y el portal.
//
// ★ POR QUE TRES BOTONES Y NO UNO QUE ALTERNA
// Con dos estados no hay forma de volver a "que decida el sistema" despues de
// haber tocado el interruptor una vez, y esa es justamente la opcion correcta
// para la mayoria: la que hace que el panel se ponga oscuro solo cuando se
// pone oscuro todo lo demas.

const OPCIONES = [
  { valor: "sistema", etiqueta: "Igual que el sistema", Icono: IconoSistema },
  { valor: "claro", etiqueta: "Claro", Icono: IconoSol },
  { valor: "oscuro", etiqueta: "Oscuro", Icono: IconoLuna },
] as const satisfies readonly { valor: Tema; etiqueta: string; Icono: typeof IconoSol }[];

function aplicar(tema: Tema) {
  const html = document.documentElement;
  // "sistema" se representa por AUSENCIA del atributo, no por un valor: es lo
  // que deja que mande el `color-scheme: light dark` de :root.
  if (tema === "sistema") html.removeAttribute("data-tema");
  else html.setAttribute("data-tema", tema);

  try {
    if (tema === "sistema") localStorage.removeItem(CLAVE_TEMA);
    else localStorage.setItem(CLAVE_TEMA, tema);
  } catch {
    // Ventana privada o cookies bloqueadas: el tema vale para esta pestania y
    // no se recuerda. Es degradado aceptable; no hay nada que avisarle a nadie.
  }
}

export function InterruptorDeTema() {
  // ★ Arranca SIEMPRE en "sistema" y se corrige en el efecto. El servidor no
  // puede saber que eligio esta persona -el dato vive en su localStorage-, asi
  // que cualquier otra cosa seria adivinar y romper la hidratacion.
  const [tema, setTema] = useState<Tema>("sistema");

  useEffect(() => {
    const guardado = document.documentElement.getAttribute("data-tema");
    if (guardado === "claro" || guardado === "oscuro") setTema(guardado);
  }, []);

  function elegir(nuevo: Tema) {
    setTema(nuevo);
    aplicar(nuevo);
  }

  return (
    <div
      role="group"
      aria-label="Tema"
      className="inline-flex items-center gap-0.5 rounded-control border border-borde bg-superficie p-0.5"
    >
      {OPCIONES.map(({ valor, etiqueta, Icono }) => {
        const activo = tema === valor;
        return (
          <button
            key={valor}
            type="button"
            onClick={() => elegir(valor)}
            aria-pressed={activo}
            title={etiqueta}
            aria-label={etiqueta}
            className={`rounded-[calc(var(--radio-control)-2px)] p-1.5 transition-colors ${
              activo
                ? "bg-superficie-2 text-texto"
                : "text-texto-tenue hover:text-texto-suave"
            }`}
          >
            <Icono className="size-3.5" />
          </button>
        );
      })}
    </div>
  );
}
