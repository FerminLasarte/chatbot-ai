import "server-only";

// Las dos rutas publicas de la API: las usa el CLIENTE de la agencia, no la
// agencia.
//
// ★ Este archivo esta separado de lib/api.ts a proposito, y no es cosmetico.
// Alla toda peticion sale firmada con ADMIN_API_KEY, que puede leer y borrar
// datos de TODOS los clientes. Aca no hay ninguna clave: la autorizacion es el
// token que viene en la URL del link, y su alcance es unicamente conectarle un
// WhatsApp a ese cliente. Mezclar las dos cosas en un mismo modulo hace muy
// facil que un `pedir()` de mas termine mandando la clave admin a una pagina
// que abre cualquiera con un link.

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type EstadoOnboarding = {
  nombre_cliente: string;
  app_id: string;
  config_id: string;
  api_version: string;
  ya_conectado: boolean;
};

export type ResultadoOnboarding = {
  conectado: boolean;
  advertencia: string | null;
};

/** Un error que ya viene redactado para que lo lea el cliente final. */
export class ErrorOnboarding extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function pedirSinClave<T>(ruta: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1${ruta}`, {
      ...init,
      cache: "no-store",
    });
  } catch {
    throw new ErrorOnboarding("No se pudo conectar con el servidor. Proba de nuevo.", 503);
  }

  if (!res.ok) {
    let detalle = "No se pudo completar la operacion.";
    try {
      const cuerpo = await res.json();
      // La API redacta estos mensajes pensando en el cliente final: se muestran
      // tal cual en vez de traducirlos otra vez aca.
      if (typeof cuerpo.detail === "string") detalle = cuerpo.detail;
    } catch {
      /* se queda el generico */
    }
    throw new ErrorOnboarding(detalle, res.status);
  }

  return (await res.json()) as T;
}

export const verEstadoOnboarding = (token: string) =>
  pedirSinClave<EstadoOnboarding>(`/onboarding/${encodeURIComponent(token)}`);

export const conectarWhatsAppDelCliente = (
  token: string,
  datos: { code: string; waba_id: string; phone_number_id: string },
) =>
  pedirSinClave<ResultadoOnboarding>(`/onboarding/${encodeURIComponent(token)}/conectar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
