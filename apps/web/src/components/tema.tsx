"use client";

import { useSyncExternalStore } from "react";

import { IconoLuna, IconoSistema, IconoSol } from "@/components/iconos";
import { CLAVE_TEMA, type Tema } from "@/lib/tema";

// El interruptor de tema. Vive en las dos pieles: el panel y el portal.
//
// ★ POR QUE TRES BOTONES Y NO UNO QUE ALTERNA
// Con dos estados no hay forma de volver a "que decida el sistema" despues de
// haber tocado el interruptor una vez, y esa es justamente la opcion correcta
// para la mayoria: la que hace que el panel se ponga oscuro solo cuando se
// pone oscuro todo lo demas.
//
// ★ POR QUE useSyncExternalStore Y NO useState + useEffect
// El tema no es estado de React: es un atributo del <html> que ya viene puesto
// desde antes del primer pintado (ver lib/tema.ts). Copiarlo a un useState
// dentro de un efecto crea una segunda fuente de verdad que hay que mantener
// sincronizada, y ademas obliga a un render de mas en cada carga. Con
// useSyncExternalStore el DOM es el unico dueno del valor y React se limita a
// leerlo, que es exactamente para lo que existe este hook.

const OPCIONES = [
  { valor: "sistema", etiqueta: "Igual que el sistema", Icono: IconoSistema },
  { valor: "claro", etiqueta: "Claro", Icono: IconoSol },
  { valor: "oscuro", etiqueta: "Oscuro", Icono: IconoLuna },
] as const satisfies readonly { valor: Tema; etiqueta: string; Icono: typeof IconoSol }[];

/** Los que quieren enterarse cuando cambia. Solo cambia desde este componente:
 *  no existe ningun evento del navegador para "cambio de atributo propio". */
const oyentes = new Set<() => void>();

function suscribir(alCambiar: () => void): () => void {
  oyentes.add(alCambiar);
  return () => {
    oyentes.delete(alCambiar);
  };
}

/** El valor vive en el DOM, puesto por el guion de lib/tema.ts. */
function leer(): Tema {
  const puesto = document.documentElement.getAttribute("data-tema");
  return puesto === "claro" || puesto === "oscuro" ? puesto : "sistema";
}

/** En el servidor no hay eleccion posible: manda el sistema operativo.
 *
 *  ★ React usa esto para el render de hidratacion y despues re-renderiza con
 *  el valor real del cliente. Es lo que evita el "text content did not match"
 *  sin tener que suprimir el aviso. */
function leerEnServidor(): Tema {
  return "sistema";
}

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

  for (const avisar of oyentes) avisar();
}

export function InterruptorDeTema() {
  const tema = useSyncExternalStore(suscribir, leer, leerEnServidor);

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
            onClick={() => aplicar(valor)}
            aria-pressed={activo}
            title={etiqueta}
            aria-label={etiqueta}
            className={`rounded-[calc(var(--radio-control)-2px)] p-1.5 transition-colors ${
              activo ? "bg-superficie-2 text-texto" : "text-texto-tenue hover:text-texto-suave"
            }`}
          >
            <Icono className="size-3.5" />
          </button>
        );
      })}
    </div>
  );
}
