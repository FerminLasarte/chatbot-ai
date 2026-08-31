"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import { duracion } from "@/lib/duracion";

// El hilo de una conversacion, en un panel que entra desde la derecha.
//
// POR QUE UN PANEL Y NO UNA PAGINA
// --------------------------------
// Quien mira esto casi siempre esta comparando: "de estas cinco conversaciones,
// cual es la que salio mal". Una pagina aparte obliga a ir y volver, y en cada
// vuelta hay que reencontrar donde estaba. El panel deja la lista a la vista y
// convierte esa comparacion en un par de clics. En un telefono no hay lista que
// preservar, asi que ocupa toda la pantalla.
//
// POR QUE VIVE EN /components Y NO EN LA CARPETA DE UNA RUTA
// ----------------------------------------------------------
// Lo usan las dos puertas: el duenio del negocio en /mi-negocio y la agencia en
// /panel. Es el mismo hilo y tiene que verse igual; lo unico que cambia es de
// donde salen los datos -cada ruta pasa su propia funcion, con su propia
// credencial- y como se nombra al que contesto a mano.

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
  // Separado de `estado` a proposito: la animacion de entrada necesita un frame
  // con el panel ya montado pero todavia corrido.
  const [entrando, setEntrando] = useState(false);
  const fondo = useRef<HTMLDivElement>(null);
  const cerrar1 = useRef<HTMLButtonElement>(null);
  const cuerpo = useRef<HTMLDivElement>(null);

  const abierto = estado.paso !== "cerrado";

  const cerrar = useCallback(() => {
    setEntrando(false);
    setEstado({ paso: "cerrado" });
  }, []);

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

  // Escape cierra, y mientras el panel esta abierto la pagina de atras no
  // scrollea: sin esto, en el telefono el dedo mueve la lista en vez del hilo.
  useEffect(() => {
    if (!abierto) return;

    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === "Escape") cerrar();
    };
    window.addEventListener("keydown", alTeclear);

    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const id = window.setTimeout(() => {
      setEntrando(true);
      cerrar1.current?.focus();
    }, 10);

    return () => {
      window.removeEventListener("keydown", alTeclear);
      document.body.style.overflow = overflow;
      clearTimeout(id);
    };
  }, [abierto, cerrar]);

  // Un hilo se abre por el final, como cualquier chat: lo ultimo que se dijo es
  // lo que se vino a leer. Sin esto, en una conversacion de meses hay que
  // scrollear hasta abajo cada vez.
  useEffect(() => {
    if (estado.paso !== "listo" || !cuerpo.current) return;
    cuerpo.current.scrollTop = cuerpo.current.scrollHeight;
  }, [estado]);

  return (
    <>
      <button
        type="button"
        onClick={abrir}
        className="rounded-md px-2 py-1 text-xs text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
      >
        Ver conversaci&oacute;n
      </button>

      {abierto && (
        <div className="fixed inset-0 z-50">
          {/* ★ El velo es HERMANO del panel, no su padre. Anidado, el
              `backdrop-blur` del velo alcanza tambien al contenido del panel y
              el hilo se lee borroso: backdrop-filter afecta a todo lo que se
              pinta encima dentro de su contexto. Se vio en la primera prueba. */}
          <div
            ref={fondo}
            onClick={cerrar}
            className={`absolute inset-0 bg-zinc-900/20 backdrop-blur-[2px] transition-opacity duration-200 motion-reduce:transition-none ${
              entrando ? "opacity-100" : "opacity-0"
            }`}
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label={`Conversacion con ${titulo}`}
            className={`absolute inset-y-0 right-0 flex w-full flex-col border-zinc-200 bg-white shadow-2xl transition-transform duration-200 ease-out motion-reduce:transition-none sm:max-w-md sm:border-l dark:border-zinc-800 dark:bg-zinc-950 ${
              entrando ? "translate-x-0" : "translate-x-full"
            }`}
          >
            {/* Encabezado fijo: con el hilo scrolleado sigue diciendo con quien
                se esta hablando, que es justo lo que uno pierde de vista. */}
            <header className="flex items-start justify-between gap-3 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
              <div className="min-w-0">
                <h2 className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {titulo}
                </h2>
                <p className="mt-0.5 text-xs text-zinc-500">{subtitulo}</p>
              </div>
              <button
                ref={cerrar1}
                type="button"
                onClick={cerrar}
                aria-label="Cerrar"
                className="-mr-2 -mt-1 rounded-md px-2 py-1 text-lg leading-none text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              >
                &times;
              </button>
            </header>

            <div ref={cuerpo} className="flex-1 overflow-y-auto overscroll-contain px-5 py-4">
              {estado.paso === "cargando" && <Esqueleto />}

              {estado.paso === "error" && (
                <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
                  {estado.mensaje}
                </p>
              )}

              {estado.paso === "listo" &&
                (estado.mensajes.length === 0 ? (
                  <p className="text-sm text-zinc-500">
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

            {children && (
              <footer className="border-t border-zinc-200 px-5 py-4 dark:border-zinc-800">
                {children}
              </footer>
            )}
          </aside>
        </div>
      )}
    </>
  );
}

/** Mientras carga: la forma del hilo, sin contenido inventado. */
function Esqueleto() {
  return (
    <div className="flex animate-pulse flex-col gap-3" aria-label="Cargando la conversacion">
      <div className="h-10 w-3/5 rounded-2xl bg-zinc-100 dark:bg-zinc-900" />
      <div className="h-14 w-4/5 self-end rounded-2xl bg-zinc-100 dark:bg-zinc-900" />
      <div className="h-10 w-2/5 rounded-2xl bg-zinc-100 dark:bg-zinc-900" />
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
            ? "rounded-bl-md bg-zinc-100 text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100"
            : "rounded-br-md bg-blue-50 text-zinc-900 dark:bg-blue-950/50 dark:text-zinc-100"
        }`}
      >
        {mensaje.content}
      </div>
      <span className="px-1 text-[11px] text-zinc-400">
        {quien && `${quien} · `}hace {duracion(mensaje.minutos)}
      </span>
    </li>
  );
}
