// La forma de una conversacion y las dos cuentas que se hacen sobre una lista.
//
// ★ POR QUE ESTO NO VIVE EN components/conversaciones.tsx
// Ese archivo pasa a ser un componente de cliente -filtrar y buscar tienen que
// ser instantaneos-, y un modulo marcado con "use client" exporta REFERENCIAS,
// no valores: un componente de servidor que importara `cuantasEsperan` de ahi
// recibiria un proxy y explotaria al llamarlo. Las dos puertas cuentan las que
// esperan del lado del servidor, para poder titular la pantalla con eso.

/** Lo minimo que la lista necesita saber de una conversacion.
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
  ventana_abierta: boolean;
  minutos_de_ventana: number | null;
};

/** Cuantas estan esperando que alguien las atienda. */
export function cuantasEsperan(conversaciones: readonly ConversacionEnLista[]): number {
  return conversaciones.filter((c) => c.derivada).length;
}

/** Las que piden una persona, primero.
 *
 *  ★ El resto conserva el orden que manda la API (la ultima actividad primero).
 *  Enterrado entre veinte conversaciones ordenadas por fecha, un pedido de
 *  ayuda no sirve de nada.
 *
 *  Entre las que esperan manda la que espera hace mas: es la que esta mas cerca
 *  de que el cliente se canse y no vuelva. */
export function conLasQueEsperanPrimero<T extends ConversacionEnLista>(
  conversaciones: readonly T[],
): T[] {
  return [...conversaciones].sort((a, b) => {
    if (a.derivada !== b.derivada) return Number(b.derivada) - Number(a.derivada);
    if (!a.derivada) return 0;
    return (b.minutos_desde_derivacion ?? 0) - (a.minutos_desde_derivacion ?? 0);
  });
}

/** Como se muestra un numero de WhatsApp. */
export function comoSeLlama(conversacion: ConversacionEnLista): string {
  return conversacion.channel === "whatsapp"
    ? `+${conversacion.external_id}`
    : conversacion.external_id;
}
