import "server-only";

// Las rutas del portal del cliente: las usa el DUENIO DEL NEGOCIO, no la agencia.
//
// ★ Este archivo esta separado de lib/api.ts a proposito, por el mismo motivo
// que lib/onboarding.ts. Alla toda peticion sale firmada con ADMIN_API_KEY, que
// puede leer y borrar datos de TODOS los clientes. Aca la credencial es la clave
// `client_portal` del propio cliente, que solo alcanza para ver sus
// conversaciones y pausar su bot. Mezclar las dos cosas en un mismo modulo hace
// muy facil que un `pedir()` de mas termine mandando la clave admin en nombre de
// alguien que entro con un link.
//
// Fijate que ninguna funcion de aca recibe un tenantId: no hay ninguno que
// mandar. La API deduce el cliente de la clave (ver routes/portal.py), asi que
// no existe el parametro que habria que acordarse de validar.

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type NegocioDelPortal = { nombre: string };

/** Igual que `Conversacion` de lib/api.ts: es el mismo `ConversationRead`. */
export type ConversacionDelPortal = {
  id: string;
  channel: string;
  external_id: string;
  last_activity_at: string;
  pausada_hasta: string | null;
  /** Los tres derivados los calcula la API, que es la que tiene el reloj bien
   *  puesto. Ver la nota de `Conversacion` en lib/api.ts. */
  en_modo_manual: boolean;
  /** El asistente pidio que intervenga una persona, y hace cuanto. Sigue en
   *  true aunque la pausa haya vencido: mientras nadie atienda, sigue pendiente. */
  derivada: boolean;
  minutos_desde_derivacion: number | null;
  minutos_inactiva: number;
  minutos_restantes: number | null;
  mensajes: number;
  ultimo_mensaje: string | null;
};

/** Un mensaje del hilo. Es el `MessageRead` de la API. */
export type MensajeDelHilo = {
  id: string;
  /** "user" = el cliente final; "assistant" = el negocio. */
  role: string;
  /** Quien escribio los del negocio: "bot", "persona", o null en los mensajes
   *  anteriores a que la API empezara a anotarlo. */
  autor: string | null;
  content: string;
  created_at: string;
  /** Antiguedad en minutos, calculada por la API. Ver la nota de arriba. */
  minutos: number;
};

/** Un error ya redactado para que lo lea el duenio del negocio. */
export class ErrorPortal extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** La clave ya no sirve (revocada, o el cliente quedo desactivado). */
export class AccesoRevocado extends ErrorPortal {}

async function pedir<T>(clave: string, ruta: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/portal${ruta}`, {
      ...init,
      headers: { Authorization: `Bearer ${clave}`, ...init.headers },
      cache: "no-store", // el estado de la pausa nunca puede mostrarse viejo
    });
  } catch {
    throw new ErrorPortal("No se pudo conectar con el servidor. Proba de nuevo.", 503);
  }

  // 401 y 403 son el mismo hecho para quien esta mirando: el link dejo de
  // servir. Se distingue del resto porque la pagina tiene que decirle que pida
  // uno nuevo, no que reintente.
  if (res.status === 401 || res.status === 403) {
    throw new AccesoRevocado("Este link ya no tiene acceso.", res.status);
  }

  if (!res.ok) {
    let detalle = "No se pudo completar la operacion.";
    try {
      const cuerpo = await res.json();
      if (typeof cuerpo.detail === "string") detalle = cuerpo.detail;
    } catch {
      /* se queda el generico */
    }
    throw new ErrorPortal(detalle, res.status);
  }

  return (await res.json()) as T;
}

/** Tambien sirve para validar la clave: si responde, el link es bueno. */
export const verMiNegocio = (clave: string) => pedir<NegocioDelPortal>(clave, "/me");

export const listarMisConversaciones = (clave: string) =>
  pedir<ConversacionDelPortal[]>(clave, "/conversations");

export const verMiConversacion = (clave: string, conversacionId: string) =>
  pedir<MensajeDelHilo[]>(clave, `/conversations/${conversacionId}/messages`);

export const pausarMiBot = (clave: string, conversacionId: string, horas: number) =>
  pedir<ConversacionDelPortal>(clave, `/conversations/${conversacionId}/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ horas }),
  });

export const reanudarMiBot = (clave: string, conversacionId: string) =>
  pedir<ConversacionDelPortal>(clave, `/conversations/${conversacionId}/manual`, {
    method: "DELETE",
  });
