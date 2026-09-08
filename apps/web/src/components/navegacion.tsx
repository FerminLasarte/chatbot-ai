"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// La navegacion entre las secciones de algo. La usan las dos puertas.
//
// ★ POR QUE ESTA EN components/ Y NO ADENTRO DEL PANEL
// Nacio en el panel, donde un cliente tiene cinco secciones. El portal era una
// sola pantalla y no necesitaba ninguna. En cuanto el portal tenga dos -las
// conversaciones y la ficha del negocio- va a necesitar exactamente esta pieza,
// y si no esta aca se va a escribir una segunda version al lado: el mismo error
// que este repo ya se comio una vez con los botones.
//
// Es presentacional: recibe las secciones y no sabe de que son.

export type Seccion = {
  /** El destino completo. Lo arma quien la usa: aca no se conocen las rutas. */
  href: string;
  etiqueta: string;
  /** Un numero al costado -conversaciones esperando, por ejemplo-. Solo se
   *  dibuja si es mayor que cero: un "0" permanente es ruido. */
  cuantos?: number;
};

export function Navegacion({
  secciones,
  className = "",
}: {
  /** ★ El orden es el DE USO, no el alfabetico ni el de la base. Lo que se
   *  mira todos los dias va primero; lo que se toca una vez por cliente,
   *  despues. Quien la usa es responsable de ese orden. */
  secciones: readonly Seccion[];
  className?: string;
}) {
  const actual = usePathname();

  return (
    <nav
      className={`-mx-1 flex gap-1 overflow-x-auto lg:mx-0 lg:flex-col lg:overflow-visible ${className}`}
    >
      {secciones.map(({ href, etiqueta, cuantos }) => {
        const activa = actual === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={activa ? "page" : undefined}
            className={`flex shrink-0 items-center justify-between gap-2 rounded-control px-3 py-1.5 text-sm transition-colors ${
              activa
                ? "bg-superficie-2 font-medium text-texto"
                : "text-texto-suave hover:bg-superficie-2 hover:text-texto"
            }`}
          >
            {etiqueta}
            {cuantos !== undefined && cuantos > 0 && (
              <span className="tabular rounded-full bg-alerta-suave px-1.5 text-[11px] font-medium text-alerta">
                {cuantos}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
