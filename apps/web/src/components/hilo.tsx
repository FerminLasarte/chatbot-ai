"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import { IconoEnviar } from "@/components/iconos";
import { PanelLateral } from "@/components/panel-lateral";
import { Esqueleto } from "@/components/ui";
import { duracion } from "@/lib/duracion";

// El hilo de una conversacion: los mensajes, quien escribio cada uno, y la
// caja para contestar.
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

/** Manda una respuesta. Cada lado pasa la suya, con su credencial. */
export type Responder = (
  conversacionId: string,
  texto: string,
) => Promise<{ mensaje?: MensajeDelHilo; error?: string }>;

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
  responder,
  ventanaAbierta,
  minutosDeVentana,
  children,
  disparador,
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
  /** La accion que manda una respuesta. Sin ella el hilo es de solo lectura. */
  responder?: Responder;
  /** Si WhatsApp todavia deja mandar texto libre en esta conversacion. */
  ventanaAbierta?: boolean;
  /** Cuanto queda de esa ventana, en minutos. */
  minutosDeVentana?: number | null;
  /** Acciones al pie del panel (pausar, reanudar). Las pone quien lo usa. */
  children?: React.ReactNode;
  /** Que dice el boton que abre el panel. */
  disparador?: React.ReactNode;
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

  /** Lo que acaba de salir se agrega al hilo sin volver a pedirlo entero. */
  const agregar = useCallback((mensaje: MensajeDelHilo) => {
    setEstado((previo) =>
      previo.paso === "listo"
        ? { paso: "listo", mensajes: [...previo.mensajes, mensaje] }
        : previo,
    );
  }, []);

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
        className="shrink-0 rounded-control px-2 py-1 text-xs text-texto-suave transition-colors hover:bg-superficie-2 hover:text-texto"
      >
        {disparador ?? "Ver conversación"}
      </button>

      <PanelLateral
        abierto={estado.paso !== "cerrado"}
        titulo={titulo}
        subtitulo={subtitulo}
        alCerrar={cerrar}
        pie={
          <div className="flex flex-col gap-3">
            {children}
            {responder && (
              <CajaDeRespuesta
                conversacionId={conversacionId}
                responder={responder}
                ventanaAbierta={ventanaAbierta ?? false}
                minutosDeVentana={minutosDeVentana ?? null}
                alEnviar={agregar}
              />
            )}
          </div>
        }
      >
        <div ref={cuerpo} className="flex-1 overflow-y-auto overscroll-contain px-5 py-4">
          {estado.paso === "cargando" && <EsqueletoDelHilo />}

          {estado.paso === "error" && (
            <p className="rounded-control bg-error-suave px-3 py-2 text-sm text-error">
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
function EsqueletoDelHilo() {
  return (
    <div className="flex flex-col gap-3" aria-label="Cargando la conversación">
      <Esqueleto className="h-10 w-3/5 rounded-2xl" />
      <Esqueleto className="h-14 w-4/5 self-end rounded-2xl" />
      <Esqueleto className="h-10 w-2/5 rounded-2xl" />
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
      <span className="tabular px-1 text-[11px] text-texto-tenue">
        {quien && `${quien} · `}hace {duracion(mensaje.minutos)}
      </span>
    </li>
  );
}

/**
 * La caja para contestarle al cliente final.
 *
 * ★ POR QUE LA VENTANA DE 24 h SE MUESTRA ANTES Y NO DESPUES DE ENVIAR
 * Fuera de esa ventana Meta rechaza el texto libre. Sin este cartel, alguien
 * escribe una respuesta larga, la manda, y recien ahi aparece un error -el de
 * Meta, en ingles, hablando de plantillas-. Con la ventana ya resuelta por la
 * API (`ventana_abierta`), la caja no deja escribir y explica que hacer.
 */
function CajaDeRespuesta({
  conversacionId,
  responder,
  ventanaAbierta,
  minutosDeVentana,
  alEnviar,
}: {
  conversacionId: string;
  responder: Responder;
  ventanaAbierta: boolean;
  minutosDeVentana: number | null;
  alEnviar: (mensaje: MensajeDelHilo) => void;
}) {
  const [texto, setTexto] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, iniciar] = useTransition();
  const campo = useRef<HTMLTextAreaElement>(null);

  function enviar() {
    const limpio = texto.trim();
    if (!limpio || enviando) return;
    setError(null);

    iniciar(async () => {
      const r = await responder(conversacionId, limpio);
      if (r.error || !r.mensaje) {
        setError(r.error ?? "No se pudo enviar el mensaje.");
        return;
      }
      // ★ Recien se vacia con el mensaje ya confirmado por la API. Limpiando al
      // apretar Enviar, un fallo de Meta se lleva puesto lo que alguien acaba
      // de escribir y no hay forma de recuperarlo.
      setTexto("");
      alEnviar(r.mensaje);
      campo.current?.focus();
    });
  }

  if (!ventanaAbierta) {
    return (
      <p className="rounded-control bg-superficie-2 px-3 py-2 text-xs text-texto-suave">
        {minutosDeVentana === null
          ? "Todavía no escribió nadie en esta conversación, así que no hay a quién contestarle."
          : "Pasaron más de 24 h desde el último mensaje del cliente y WhatsApp ya no deja escribirle. Hasta que vuelva a escribir él, solo se lo puede contactar con una plantilla aprobada por Meta."}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-end gap-2">
        <textarea
          ref={campo}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            // Enter manda y Shift+Enter hace un salto de linea, como en
            // cualquier chat. Sin esto hay que ir al boton con el mouse en cada
            // respuesta, que es parte de por que se termina contestando desde
            // el celular en vez de desde aca.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              enviar();
            }
          }}
          rows={2}
          disabled={enviando}
          placeholder="Escribí tu respuesta…"
          className="max-h-40 w-full resize-y rounded-control border border-borde bg-superficie px-3 py-2 text-sm text-texto transition-colors placeholder:text-texto-tenue hover:border-borde-fuerte focus:border-acento focus:outline-none disabled:opacity-60"
        />
        <button
          type="button"
          onClick={enviar}
          disabled={enviando || texto.trim() === ""}
          aria-label="Enviar respuesta"
          className="inline-flex items-center justify-center rounded-control bg-acento px-3 py-2.5 text-sobre-acento shadow-panel transition-colors hover:bg-acento-fuerte disabled:pointer-events-none disabled:opacity-40"
        >
          <IconoEnviar className="size-4" />
        </button>
      </div>

      <p className="text-[11px] text-texto-tenue">
        {enviando ? (
          "Enviando…"
        ) : (
          <>
            Enter manda, Shift+Enter hace un salto de línea.
            {minutosDeVentana !== null && (
              <> Se le puede escribir por {duracion(minutosDeVentana)} más.</>
            )}
          </>
        )}
      </p>

      {error && (
        <p role="status" className="rounded-control bg-error-suave px-3 py-2 text-xs text-error">
          {error}
        </p>
      )}
    </div>
  );
}
