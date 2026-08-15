"use client";

import { useActionState } from "react";

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
  const estilos = {
    normal:
      "bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300",
    suave:
      "border border-zinc-300 text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800",
  }[variante];

  return (
    <button
      type="submit"
      className={`rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:opacity-40 ${estilos}`}
    >
      {children}
    </button>
  );
}

function Aviso({ estado }: { estado: EstadoPortal }) {
  if (!estado.error && !estado.ok) return null;
  const esError = Boolean(estado.error);
  return (
    <p
      role="status"
      className={`mt-2 rounded-md px-3 py-2 text-sm ${
        esError
          ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
          : "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300"
      }`}
    >
      {estado.error ?? estado.ok}
    </p>
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
      <Aviso estado={estado} />
    </form>
  );
}
