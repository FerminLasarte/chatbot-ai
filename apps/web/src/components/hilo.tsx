"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import { PanelLateral } from "@/components/panel-lateral";
import { duracion } from "@/lib/duracion";

// El hilo de una conversacion: los mensajes y quien escribio cada uno.
//
// El panel que lo contiene vive en components/panel-lateral.tsx. Aca queda solo
// lo propio de una conversacion, que es lo que hace que las dos puertas -el
// portal del cliente y el panel de la agencia- muestren exactamente lo mismo.
// Lo unico que cambia entre ellas es de donde salen los datos (cada ruta pasa
// su funcion, con su credencial) y como se nombra a quien contesto a mano.

/** Un mensaje ya listo para mostrar. Es el `MessageRead` de la API. */
export type MensajeDelHilo = {
  id: string;
  /** "user" = el cliente final; "assistant" = el negocio. */
  role: string;
  /** "bot" | "persona" | null (mensajes anteriores a que se anotara). */
  autor: string | null;
  content: string;
  minutos: number;
};

type Resultado = { mensajes?: MensajeDelHilo[]; error?: string };

type Estado =
  | { paso: "cerrado" }
  | { paso: "cargando" }
  | { paso: "listo"; mensajes: MensajeDelHilo[] }
  | { paso: "error"; mensaje: string };

export function VerConversacion({
  conversacionId,
  titulo,
  subtitulo,
  etiquetaPersona,
  traer,
  children,
}: {
  conversacionId: string;
  /** Con quien es la conversacion. Encabeza el panel. */
  titulo: string;
  /** Una linea de contexto: cantidad de mensajes, hace cuanto. */
  subtitulo: string;
  /** Como llamar a quien contesto a mano: "Vos" en el portal del negocio, "A
   *  mano" en el panel de la agencia, donde esa persona es un tercero. */
  etiquetaPersona: string;
  /** La accion de servidor que trae el hilo. Cada ruta pasa la suya, con su
   *  credencial; este componente nunca sabe cual es. */
  traer: (conversacionId: string) => Promise<Resultado>;
  /** Acciones al pie del panel (pausar, reanudar). Las pone quien lo usa. */
  children?: React.ReactNode;
}) {
  const [estado, setEstado] = useState<Estado>({ paso: "cerrado" });
  const cuerpo = useRef<HTMLDivElement>(null);

  // ★ La accion de servidor va dentro de una transicion, como pide la guia de
  // Next para invocarlas fuera de un <form>. Ademas es lo correcto de por si:
  // traer el hilo no es urgente y no tiene por que bloquear la interfaz, que
  // mientras tanto ya esta mostrando el panel con su esqueleto.
  const [, iniciar] = useTransition();

  const abrir = useCallback(() => {
    setEstado({ paso: "cargando" });
    iniciar(async () => {
      const r = await traer(conversacionId);
      setEstado(
        r.error
          ? { paso: "error", mensaje: r.error }
          : { paso: "listo", mensajes: r.mensajes ?? [] },
      );
    });
  }, [conversacionId, traer]);

  const cerrar = useCallback(() => setEstado({ paso: "cerrado" }), []);

  // Un hilo se abre por el final, como cualquier chat: lo ultimo que se dijo es
  // lo que se vino a leer.
  useEffect(() => {
    if (estado.paso !== "listo" || !cuerpo.current) return;
    cuerpo.current.scrollTop = cuerpo.current.scrollHeight;
  }, [estado]);

  return (
    <>
      <button
        type="button"
        onClick={abrir}
        className="shrink-0 rounded-lg px-2 py-1 text-xs text-texto-suave transition-colors hover:bg-superficie-2 hover:text-texto"
      >
        Ver conversaci&oacute;n
      </button>

      <PanelLateral
        abierto={estado.paso !== "cerrado"}
        titulo={titulo}
        subtitulo={subtitulo}
        alCerrar={cerrar}
        pie={children}
      >
        <div ref={cuerpo} className="flex-1 overflow-y-auto overscroll-contain px-5 py-4">
          {estado.paso === "cargando" && <Esqueleto />}

          {estado.paso === "error" && (
            <p className="rounded-lg bg-error-suave px-3 py-2 text-sm text-error">
              {estado.mensaje}
            </p>
          )}

          {estado.paso === "listo" &&
            (estado.mensajes.length === 0 ? (
              <p className="text-sm text-texto-suave">
                Esta conversaci&oacute;n todav&iacute;a no tiene mensajes.
              </p>
            ) : (
              <ol className="flex flex-col gap-3">
                {estado.mensajes.map((m) => (
                  <Mensaje key={m.id} mensaje={m} etiquetaPersona={etiquetaPersona} />
                ))}
              </ol>
            ))}
        </div>
      </PanelLateral>
    </>
  );
}

/** Mientras carga: la forma del hilo, sin contenido inventado. */
function Esqueleto() {
  return (
    <div className="flex animate-pulse flex-col gap-3" aria-label="Cargando la conversacion">
      <div className="h-10 w-3/5 rounded-2xl bg-superficie-2" />
      <div className="h-14 w-4/5 self-end rounded-2xl bg-superficie-2" />
      <div className="h-10 w-2/5 rounded-2xl bg-superficie-2" />
    </div>
  );
}

function Mensaje({
  mensaje,
  etiquetaPersona,
}: {
  mensaje: MensajeDelHilo;
  etiquetaPersona: string;
}) {
  const delCliente = mensaje.role === "user";

  // ★ La atribucion es el motivo de esta pantalla. El bot y la persona escriben
  // los dos con rol "assistant" -para el cliente final las dos cosas son "me
  // contesto el negocio"-, asi que sin este cartelito el duenio audita al
  // asistente leyendo sus propios mensajes. Cuando no se sabe (mensajes
  // anteriores a que se anotara) no se dice nada, en vez de adivinar.
  const quien = delCliente
    ? null
    : mensaje.autor === "bot"
      ? "Asistente"
      : mensaje.autor === "persona"
        ? etiquetaPersona
        : null;

  return (
    <li className={`flex flex-col gap-1 ${delCliente ? "items-start" : "items-end"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap ${
          delCliente
            ? "rounded-bl-md bg-superficie-2 text-texto"
            : "rounded-br-md bg-acento-suave text-texto"
        }`}
      >
        {mensaje.content}
      </div>
      <span className="px-1 text-[11px] text-texto-tenue">
        {quien && `${quien} · `}hace {duracion(mensaje.minutos)}
      </span>
    </li>
  );
}
