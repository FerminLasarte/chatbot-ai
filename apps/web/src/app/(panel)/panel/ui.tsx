"use client";

import { useActionState, useState } from "react";

import { Aviso as AvisoVisual, claseBoton, claseCampo } from "@/components/ui";
import type { Estado } from "./acciones";

const VACIO: Estado = {};

export function Boton({
  children,
  variante = "normal",
}: {
  children: React.ReactNode;
  variante?: "normal" | "peligro" | "suave";
}) {
  // La apariencia sale de components/ui.tsx: lo que se comparte con el portal
  // es como se ve un boton, no el tipo de estado de cada lado.
  return (
    <button
      type="submit"
      className={claseBoton(variante === "normal" ? "principal" : variante)}
    >
      {children}
    </button>
  );
}

export function Aviso({ estado }: { estado: Estado }) {
  return <AvisoVisual error={estado.error} ok={estado.ok} />;
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
        <input name="name" placeholder="widget de la web" className={claseCampo} />
        <select name="scope" className={claseCampo} defaultValue="chat">
          <option value="chat">chat</option>
          <option value="tenant">tenant</option>
        </select>
      </div>
      <div>
        <Boton variante="suave">Emitir clave</Boton>
      </div>
      {estado.clave && (
        <code className="block overflow-x-auto rounded-lg bg-superficie-2 p-3 text-xs text-texto">
          {estado.clave}
        </code>
      )}
      <Aviso estado={estado} />
    </form>
  );
}

/**
 * Genera un link para mandarle al cliente y lo deja listo para copiar y pegar.
 *
 * Lo usan los dos links que existen: el de onboarding (conectar WhatsApp) y el
 * del portal (ver conversaciones y pausar el bot). Comparten componente porque
 * comparten el problema: el secreto se muestra UNA sola vez, asi que la pagina
 * tiene que dejarlo copiar bien antes de que el usuario navegue a otro lado.
 *
 * Componente propio y no un `Formulario` porque el link hay que mostrarlo y
 * copiarlo, y eso necesita estado en el cliente (ver la nota de `Formulario`
 * sobre por que esto no se puede resolver con un render-prop).
 */
export function FormularioLink({
  accion,
  tenantId,
  etiqueta,
  etiquetaRepetir,
  variante = "normal",
}: {
  accion: (estado: Estado, form: FormData) => Promise<Estado>;
  tenantId: string;
  etiqueta: string;
  etiquetaRepetir: string;
  variante?: "normal" | "suave";
}) {
  const [estado, ejecutar] = useActionState(accion, VACIO);
  const [copiado, setCopiado] = useState(false);

  async function copiar(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      // Sin permiso de portapapeles (o sin https) el link queda igual a la
      // vista para seleccionarlo a mano: no hace falta avisar nada.
    }
  }

  return (
    <form action={ejecutar} className="flex flex-col gap-3">
      <input type="hidden" name="id" value={tenantId} />
      <div>
        <Boton variante={variante}>{estado.link ? etiquetaRepetir : etiqueta}</Boton>
      </div>

      {estado.link && (
        <div className="flex flex-col gap-2">
          <code className="block overflow-x-auto rounded-lg bg-superficie-2 p-3 text-xs text-texto">
            {estado.link}
          </code>
          <div>
            <button
              type="button"
              onClick={() => copiar(estado.link!)}
              className={claseBoton("suave")}
            >
              {copiado ? "Copiado" : "Copiar link"}
            </button>
          </div>
        </div>
      )}

      <Aviso estado={estado} />
    </form>
  );
}
