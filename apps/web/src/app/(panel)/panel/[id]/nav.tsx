import { Navegacion, type Seccion } from "@/components/navegacion";

// Las secciones de un cliente dentro del panel.
//
// ★ EL ORDEN NO ES ALFABETICO NI EL DE LA BASE: ES EL DE USO
// Conversaciones primero porque es a lo que se entra todos los dias. WhatsApp y
// Conocimiento se tocan al dar de alta y despues cada tanto. Accesos y Consumo
// son de una vez cada mucho. La pagina anterior las mostraba a todas apiladas
// con el mismo peso, y el consumo del mes ocupaba tanto lugar como el hilo que
// alguien estaba esperando.
//
// El dibujo vive en components/navegacion.tsx: cuando el portal del cliente
// tenga su segunda pantalla va a necesitar la misma pieza, y una copia al lado
// es como el mismo boton termina con dos grises.

const SECCIONES = [
  { href: "", etiqueta: "Conversaciones" },
  { href: "/conocimiento", etiqueta: "Conocimiento" },
  { href: "/whatsapp", etiqueta: "WhatsApp" },
  { href: "/accesos", etiqueta: "Accesos" },
  { href: "/consumo", etiqueta: "Consumo" },
] as const;

export function NavDelCliente({
  id,
  esperando,
}: {
  id: string;
  /** Cuantas conversaciones piden una persona. Va al lado de "Conversaciones":
   *  es lo unico del nav que puede estar pidiendo algo mientras alguien mira
   *  otra seccion. */
  esperando?: number;
}) {
  const base = `/panel/${id}`;
  const secciones: Seccion[] = SECCIONES.map(({ href, etiqueta }) => ({
    href: `${base}${href}`,
    etiqueta,
    cuantos: href === "" ? esperando : undefined,
  }));

  return <Navegacion secciones={secciones} />;
}
