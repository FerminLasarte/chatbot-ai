"use client";

import { useMemo, useState } from "react";

import { IconoBuscar } from "@/components/iconos";
import { VerConversacion, type Responder } from "@/components/hilo";
import { Chip, Vacio, claseCampo } from "@/components/ui";
import {
  comoSeLlama,
  conLasQueEsperanPrimero,
  type ConversacionEnLista,
} from "@/lib/conversaciones";
import { duracion } from "@/lib/duracion";
import type { MensajeDelHilo } from "@/components/hilo";

// La lista de conversaciones, compartida por las dos puertas.
//
// ★ POR QUE ESTA COMPARTIDA SI LOS DOS LADOS SON DISTINTOS
// El panel de la agencia y el portal del cliente tienen credenciales, tipos de
// estado y formularios propios, y esa frontera es a proposito. Pero una
// conversacion es una conversacion: mostrarla distinta en cada lado no aporta
// nada y garantiza que la proxima mejora se aplique en uno solo. Lo que cambia
// entre las dos entra por props: de donde salen los mensajes, como se llama a
// quien contesto a mano, y que acciones van al pie del panel.
//
// ★ POR QUE ES UN COMPONENTE DE CLIENTE
// Filtrar y buscar tienen que responder en la tecla. Los datos los trae el
// servidor una sola vez; elegir cual de las cuarenta filas se ve es local. Las
// funciones puras que operan sobre la lista viven en lib/conversaciones.ts,
// para que las paginas de servidor tambien puedan usarlas.

/** Lo que devuelve la accion que trae un hilo. */
export type TraerHilo = (
  conversacionId: string,
) => Promise<{ mensajes?: MensajeDelHilo[]; error?: string }>;

/** Una fila de la lista, con lo que se puede hacer con ella ya dibujado.
 *
 *  ★ `acciones` es un nodo YA RENDERIZADO y no una funcion. Antes era una
 *  funcion que ejecutaba el componente de servidor; ahora que la lista corre en
 *  el navegador, una funcion no cruzaria la frontera (no es serializable). El
 *  JSX si: la pagina de servidor arma los formularios de pausa con su Server
 *  Action adentro y los manda dibujados. */
export type FilaDeConversacion = {
  conversacion: ConversacionEnLista;
  acciones?: React.ReactNode;
};

type Filtro = "todas" | "esperando" | "a-mano";

const FILTROS: { valor: Filtro; etiqueta: string }[] = [
  { valor: "todas", etiqueta: "Todas" },
  { valor: "esperando", etiqueta: "Esperando" },
  { valor: "a-mano", etiqueta: "Las atendés vos" },
];

export function ListaDeConversaciones({
  filas,
  etiquetaPersona,
  traer,
  responder,
  vacio,
}: {
  filas: readonly FilaDeConversacion[];
  /** Como llamar a quien contesto a mano desde el celular. */
  etiquetaPersona: string;
  /** Trae el hilo de una conversacion. Cada lado pasa la suya, con su credencial. */
  traer: TraerHilo;
  /** Manda una respuesta. Sin esto los hilos son de solo lectura. */
  responder?: Responder;
  /** Que decir cuando no hay ninguna. */
  vacio: { titulo: string; detalle?: string };
}) {
  const [busqueda, setBusqueda] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todas");

  const cuantas = (f: Filtro) =>
    f === "esperando"
      ? filas.filter((f2) => f2.conversacion.derivada).length
      : f === "a-mano"
        ? filas.filter((f2) => f2.conversacion.en_modo_manual).length
        : filas.length;

  const visibles = useMemo(() => {
    // Se busca por numero y por el ultimo mensaje: uno llega acordandose del
    // numero o de que se venia hablando, casi nunca de las dos cosas.
    const q = busqueda.trim().toLowerCase();
    const filtradas = filas.filter(({ conversacion: c }) => {
      if (q && !`${c.external_id} ${c.ultimo_mensaje ?? ""}`.toLowerCase().includes(q)) {
        return false;
      }
      if (filtro === "esperando") return c.derivada;
      if (filtro === "a-mano") return c.en_modo_manual;
      return true;
    });

    const orden = conLasQueEsperanPrimero(filtradas.map((f) => f.conversacion));
    const porId = new Map(filtradas.map((f) => [f.conversacion.id, f]));
    return orden.map((c) => porId.get(c.id)!);
  }, [filas, busqueda, filtro]);

  if (filas.length === 0) {
    return <Vacio titulo={vacio.titulo}>{vacio.detalle}</Vacio>;
  }

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-borde px-4 py-2.5">
        <label className="relative">
          <span className="sr-only">Buscar en las conversaciones</span>
          <IconoBuscar className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-texto-tenue" />
          <input
            type="search"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar número o mensaje"
            className={`${claseCampo} w-56 py-1.5 pl-8 text-xs`}
          />
        </label>

        <div className="flex gap-1">
          {FILTROS.map(({ valor, etiqueta }) => {
            const activo = filtro === valor;
            return (
              <button
                key={valor}
                type="button"
                onClick={() => setFiltro(valor)}
                aria-pressed={activo}
                className={`rounded-control px-2.5 py-1.5 text-xs transition-colors ${
                  activo
                    ? "bg-superficie-2 font-medium text-texto"
                    : "text-texto-suave hover:bg-superficie-2 hover:text-texto"
                }`}
              >
                {etiqueta}
                <span className="tabular ml-1.5 text-texto-tenue">{cuantas(valor)}</span>
              </button>
            );
          })}
        </div>
      </div>

      {visibles.length === 0 ? (
        <Vacio titulo="Ninguna conversación coincide">
          Probá con otro número, o cambiá el filtro.
        </Vacio>
      ) : (
        <ul>
          {visibles.map(({ conversacion, acciones }) => (
            <Fila
              key={conversacion.id}
              conversacion={conversacion}
              etiquetaPersona={etiquetaPersona}
              traer={traer}
              responder={responder}
              acciones={acciones}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/** Una fila: quien escribio, en que estado quedo y como entrar.
 *
 *  ★ Las acciones no viven aca sino al pie del panel de la conversacion. En una
 *  lista de veinte hilos, veinte desplegables y veinte botones son ruido que
 *  tapa lo unico que importa a simple vista: quien esta esperando. */
function Fila({
  conversacion,
  etiquetaPersona,
  traer,
  responder,
  acciones,
}: {
  conversacion: ConversacionEnLista;
  etiquetaPersona: string;
  traer: TraerHilo;
  responder?: Responder;
  acciones?: React.ReactNode;
}) {
  const quien = comoSeLlama(conversacion);
  const cuantos = `${conversacion.mensajes} ${
    conversacion.mensajes === 1 ? "mensaje" : "mensajes"
  }`;

  return (
    /* ★ En pantalla ancha la fila se lee como una tabla -quien, en que estado,
       cuando- y no como un parrafo pegado a la izquierda con medio monitor
       vacio al lado. En angosto vuelve a apilarse.

       La franja naranja de la izquierda es el unico adorno, y significa que
       hay alguien esperando: se ve de un vistazo, sin leer. */
    <li
      className={`flex flex-col gap-2 border-t border-borde px-4 py-fila transition-colors first:border-t-0 hover:bg-superficie-2 lg:flex-row lg:items-center lg:gap-4 ${
        conversacion.derivada ? "shadow-[inset_3px_0_0_var(--alerta)]" : ""
      }`}
    >
      <span className="min-w-0 lg:flex-1">
        <span className="tabular block truncate text-sm font-medium text-texto">{quien}</span>
        {conversacion.ultimo_mensaje && (
          <span className="mt-0.5 block truncate text-sm text-texto-suave">
            {conversacion.ultimo_mensaje}
          </span>
        )}
      </span>

      <span className="flex flex-wrap items-center gap-1.5 lg:shrink-0">
        {conversacion.derivada && (
          <Chip tono="alerta">
            Pidieron una persona
            {conversacion.minutos_desde_derivacion !== null &&
              ` · hace ${duracion(conversacion.minutos_desde_derivacion)}`}
          </Chip>
        )}
        {conversacion.minutos_restantes !== null && (
          <Chip>Lo atendés vos · vuelve en {duracion(conversacion.minutos_restantes)}</Chip>
        )}
        {/* Solo cuando esta por vencerse: decir "quedan 23 h" en cada fila es
            ruido, pero enterarse tarde de que quedaban veinte minutos es caro. */}
        {conversacion.ventana_abierta &&
          conversacion.minutos_de_ventana !== null &&
          conversacion.minutos_de_ventana < 120 && (
            <Chip tono="alerta">
              Se le puede escribir {duracion(conversacion.minutos_de_ventana)} más
            </Chip>
          )}
      </span>

      <span className="flex items-center justify-between gap-3 lg:w-64 lg:shrink-0 lg:justify-end">
        <span className="tabular text-xs whitespace-nowrap text-texto-tenue">
          {cuantos} &middot; hace {duracion(conversacion.minutos_inactiva)}
        </span>

        <VerConversacion
          conversacionId={conversacion.id}
          titulo={quien}
          subtitulo={`${cuantos} · hace ${duracion(conversacion.minutos_inactiva)}`}
          etiquetaPersona={etiquetaPersona}
          traer={traer}
          responder={responder}
          ventanaAbierta={conversacion.ventana_abierta}
          minutosDeVentana={conversacion.minutos_de_ventana}
          disparador={responder ? "Abrir" : "Ver conversación"}
        >
          {acciones}
        </VerConversacion>
      </span>
    </li>
  );
}
