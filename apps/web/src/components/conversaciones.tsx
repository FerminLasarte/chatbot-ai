import { Chip, Vacio } from "@/components/ui";
import { VerConversacion, type MensajeDelHilo } from "@/components/hilo";
import { duracion } from "@/lib/duracion";

// La lista de conversaciones, compartida por las dos puertas.
//
// ★ POR QUE ESTA COMPARTIDA SI LOS DOS LADOS SON DISTINTOS
// El panel de la agencia y el portal del cliente tienen credenciales, tipos de
// estado y formularios propios, y esa frontera es a proposito. Pero una
// conversacion es una conversacion: mostrarla distinta en cada lado no aporta
// nada y garantiza que la proxima mejora se aplique en uno solo. Lo que cambia
// entre las dos entra por props: de donde salen los mensajes, como se llama a
// quien contesto a mano, y que acciones van al pie del panel.

/** Lo que devuelve la accion que trae un hilo. */
export type TraerHilo = (
  conversacionId: string,
) => Promise<{ mensajes?: MensajeDelHilo[]; error?: string }>;

/** Lo minimo que esta lista necesita saber de una conversacion.
 *
 *  Deliberadamente estructural: tanto `Conversacion` (lib/api.ts, la agencia)
 *  como `ConversacionDelPortal` (lib/portal.ts, el cliente) lo cumplen sin
 *  tener que importarse entre si. */
export type ConversacionEnLista = {
  id: string;
  channel: string;
  external_id: string;
  en_modo_manual: boolean;
  minutos_inactiva: number;
  minutos_restantes: number | null;
  derivada: boolean;
  minutos_desde_derivacion: number | null;
  mensajes: number;
  ultimo_mensaje: string | null;
};

/** Cuantas estan esperando que alguien las atienda. */
export function cuantasEsperan(conversaciones: readonly ConversacionEnLista[]): number {
  return conversaciones.filter((c) => c.derivada).length;
}

/** Las que piden una persona, primero.
 *
 *  ★ El resto conserva el orden que manda la API (la ultima actividad primero).
 *  Enterrado entre veinte conversaciones ordenadas por fecha, un pedido de
 *  ayuda no sirve de nada. */
export function conLasQueEsperanPrimero<T extends ConversacionEnLista>(
  conversaciones: readonly T[],
): T[] {
  return [...conversaciones].sort((a, b) => Number(b.derivada) - Number(a.derivada));
}

export function ListaDeConversaciones({
  conversaciones,
  etiquetaPersona,
  traer,
  acciones,
  vacio,
}: {
  conversaciones: readonly ConversacionEnLista[];
  /** Como llamar a quien contesto a mano desde el celular. */
  etiquetaPersona: string;
  /** Trae el hilo de una conversacion. Cada lado pasa la suya, con su credencial. */
  traer: TraerHilo;
  /** Las acciones al pie del panel de cada conversacion (pausar, reanudar).
   *  Es una funcion y no un nodo porque dependen de cada fila; la ejecuta este
   *  componente, que corre en el servidor, asi que no cruza ninguna frontera. */
  acciones?: (conversacion: ConversacionEnLista) => React.ReactNode;
  /** Que decir cuando no hay ninguna. */
  vacio: string;
}) {
  if (conversaciones.length === 0) return <Vacio>{vacio}</Vacio>;

  return (
    <ul className="-my-1 flex flex-col divide-y divide-borde">
      {conLasQueEsperanPrimero(conversaciones).map((c) => (
        <Fila
          key={c.id}
          conversacion={c}
          etiquetaPersona={etiquetaPersona}
          traer={traer}
          acciones={acciones?.(c)}
        />
      ))}
    </ul>
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
  acciones,
}: {
  conversacion: ConversacionEnLista;
  etiquetaPersona: string;
  traer: TraerHilo;
  acciones?: React.ReactNode;
}) {
  const esWhatsApp = conversacion.channel === "whatsapp";
  const quien = esWhatsApp ? `+${conversacion.external_id}` : conversacion.external_id;
  const cuantos = `${conversacion.mensajes} ${
    conversacion.mensajes === 1 ? "mensaje" : "mensajes"
  }`;

  return (
    /* ★ En pantalla ancha la fila se lee como una tabla -quien, en que estado,
       cuando- y no como un parrafo pegado a la izquierda con medio monitor
       vacio al lado. En angosto vuelve a apilarse. */
    <li className="-mx-2 flex flex-col gap-2 rounded-lg px-2 py-3 transition-colors hover:bg-superficie-2 lg:flex-row lg:items-center lg:gap-6">
      <span className="min-w-0 lg:flex-1">
        <span className="truncate text-sm font-medium text-texto">{quien}</span>
        {conversacion.ultimo_mensaje && (
          <span className="mt-0.5 block truncate text-sm text-texto-suave">
            {conversacion.ultimo_mensaje}
          </span>
        )}
      </span>

      <span className="flex flex-wrap items-center gap-2 lg:shrink-0">
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
      </span>

      <span className="flex items-center justify-between gap-3 lg:w-72 lg:shrink-0 lg:justify-end">
        <span className="text-xs whitespace-nowrap text-texto-tenue">
          {cuantos} &middot; hace {duracion(conversacion.minutos_inactiva)}
        </span>

        <VerConversacion
          conversacionId={conversacion.id}
          titulo={quien}
          subtitulo={`${cuantos} · hace ${duracion(conversacion.minutos_inactiva)}`}
          etiquetaPersona={etiquetaPersona}
          traer={traer}
        >
          {acciones}
        </VerConversacion>
      </span>
    </li>
  );
}
