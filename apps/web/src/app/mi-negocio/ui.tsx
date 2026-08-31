"use client";

import { useActionState } from "react";

import { Aviso, claseBoton } from "@/components/ui";
import type { EstadoPortal } from "./acciones";

// UI propia del portal, separada de panel/ui.tsx a proposito.
//
// No es duplicacion por descuido: son dos productos para dos publicos. El
// `Estado` del panel arrastra campos que aca no existen ni tienen que existir
// (`clave`, `link`: cosas que solo emite la agencia), y compartir el componente
// obligaria a que el portal del cliente importe del arbol del panel. Mantener
// esa frontera nitida es justamente lo que hace dificil que un cambio en el
// panel filtre algo hacia la pagina que abre el cliente final.

const VACIO: EstadoPortal = {};

export function Boton({
  children,
  variante = "normal",
}: {
  children: React.ReactNode;
  variante?: "normal" | "suave";
}) {
  // La apariencia sale de components/ui.tsx: lo que se comparte es como se ve
  // un boton, no el tipo de estado de cada lado. Ver la nota de arriba.
  return (
    <button type="submit" className={claseBoton(variante === "suave" ? "suave" : "principal")}>
      {children}
    </button>
  );
}

/**
 * Formulario conectado a una Server Action, con su mensaje de resultado.
 *
 * `children` es un ReactNode, NUNCA una funcion: la pagina es un Server
 * Component y las funciones no cruzan esa frontera. Ver la nota larga en
 * panel/ui.tsx.
 */
export function FormularioPortal({
  accion,
  children,
  className = "",
}: {
  accion: (estado: EstadoPortal, form: FormData) => Promise<EstadoPortal>;
  children: React.ReactNode;
  className?: string;
}) {
  const [estado, ejecutar] = useActionState(accion, VACIO);
  return (
    <form action={ejecutar} className={className}>
      {children}
      <Aviso error={estado.error} ok={estado.ok} className="mt-2" />
    </form>
  );
}
