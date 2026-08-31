"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// La navegacion de un cliente dentro del panel.
//
// ★ EL ORDEN NO ES ALFABETICO NI EL DE LA BASE: ES EL DE USO
// Conversaciones primero porque es a lo que se entra todos los dias. WhatsApp y
// Conocimiento se tocan al dar de alta y despues cada tanto. Accesos y Consumo
// son de una vez cada mucho. La pagina anterior las mostraba a todas apiladas
// con el mismo peso, y el consumo del mes ocupaba tanto lugar como el hilo que
// alguien estaba esperando.

const SECCIONES = [
  { href: "", etiqueta: "Conversaciones" },
  { href: "/conocimiento", etiqueta: "Conocimiento" },
  { href: "/whatsapp", etiqueta: "WhatsApp" },
  { href: "/accesos", etiqueta: "Accesos" },
  { href: "/consumo", etiqueta: "Consumo" },
] as const;

export function NavDelCliente({ id }: { id: string }) {
  const actual = usePathname();
  const base = `/panel/${id}`;

  return (
    <nav className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
      {SECCIONES.map(({ href, etiqueta }) => {
        const destino = `${base}${href}`;
        const activa = actual === destino;
        return (
          <Link
            key={href}
            href={destino}
            aria-current={activa ? "page" : undefined}
            className={`shrink-0 rounded-lg px-3 py-2 text-sm transition-colors ${
              activa
                ? "bg-superficie-2 font-medium text-texto"
                : "text-texto-suave hover:bg-superficie-2 hover:text-texto"
            }`}
          >
            {etiqueta}
          </Link>
        );
      })}
    </nav>
  );
}
