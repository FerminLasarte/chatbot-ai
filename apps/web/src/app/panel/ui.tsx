"use client";

import { useActionState } from "react";

import { claseInput } from "@/lib/estilos";
import type { Estado } from "./acciones";

const VACIO: Estado = {};

export function Boton({
  children,
  variante = "normal",
}: {
  children: React.ReactNode;
  variante?: "normal" | "peligro" | "suave";
}) {
  const estilos = {
    normal:
      "bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300",
    peligro:
      "border border-red-300 text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950",
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

export function Aviso({ estado }: { estado: Estado }) {
  if (!estado.error && !estado.ok) return null;
  const esError = Boolean(estado.error);
  return (
    <p
      role="status"
      className={`rounded-md px-3 py-2 text-sm ${
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
 * `children` es un ReactNode, NUNCA una funcion: las paginas son Server
 * Components y las funciones no cruzan esa frontera (no son serializables).
 * Un render-prop aca falla en runtime con "Functions are not valid as a child
 * of Client Components". Si un formulario necesita mostrar algo derivado de su
 * estado, se hace un componente cliente propio -ver FormularioClave-.
 */
export function Formulario({
  accion,
  children,
  className = "",
}: {
  accion: (estado: Estado, form: FormData) => Promise<Estado>;
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

/** Emite una clave y la muestra: es la unica vez que el secreto es visible. */
export function FormularioClave({
  accion,
  tenantId,
}: {
  accion: (estado: Estado, form: FormData) => Promise<Estado>;
  tenantId: string;
}) {
  const [estado, ejecutar] = useActionState(accion, VACIO);
  return (
    <form action={ejecutar} className="flex flex-col gap-3">
      <input type="hidden" name="id" value={tenantId} />
      <div className="flex gap-2">
        <input name="name" placeholder="widget de la web" className={claseInput} />
        <select name="scope" className={claseInput} defaultValue="chat">
          <option value="chat">chat</option>
          <option value="tenant">tenant</option>
        </select>
      </div>
      <div>
        <Boton variante="suave">Emitir clave</Boton>
      </div>
      {estado.clave && (
        <code className="block overflow-x-auto rounded-md bg-zinc-100 p-3 text-xs dark:bg-zinc-800">
          {estado.clave}
        </code>
      )}
      <Aviso estado={estado} />
    </form>
  );
}

