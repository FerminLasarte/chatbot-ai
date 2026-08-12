import "server-only";

// Unico lugar por donde el panel habla con la API.
//
// ★ ADMIN_API_KEY no lleva el prefijo NEXT_PUBLIC_ a proposito: con el, Next la
// incrustaria en el bundle del navegador y quedaria a la vista de cualquiera
// que abra la pagina. Una clave admin expuesta permite crear, leer y borrar
// datos de TODOS los clientes. Este archivo corre solo en el servidor.

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type Tenant = {
  id: string;
  slug: string;
  name: string;
  system_prompt: string;
  is_active: boolean;
  monthly_message_limit: number | null;
};

export type Documento = { id: string; title: string; chunks: number };

export type Uso = {
  period: string;
  messages: number;
  limit: number | null;
  remaining: number | null;
};

export type ClaveCreada = {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  api_key: string;
};

export type Clave = {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  is_active: boolean;
  last_used_at: string | null;
};

export class ErrorApi extends Error {}

function claveAdmin(): string {
  const k = process.env.ADMIN_API_KEY;
  if (!k) throw new ErrorApi("falta ADMIN_API_KEY en el servidor");
  return k;
}

async function pedir<T>(ruta: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1${ruta}`, {
      ...init,
      headers: { Authorization: `Bearer ${claveAdmin()}`, ...init.headers },
      cache: "no-store", // datos de administracion: nunca servir algo viejo
    });
  } catch {
    throw new ErrorApi("no se pudo conectar con la API");
  }

  if (!res.ok) {
    // La API contesta JSON, pero un 500 sin manejar viene en texto plano:
    // parsear a ciegas taparia el error real.
    let detalle = `error ${res.status}`;
    try {
      const cuerpo = await res.json();
      detalle = cuerpo.detail ?? detalle;
    } catch {
      /* se queda el generico */
    }
    throw new ErrorApi(detalle);
  }

  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const json = { "Content-Type": "application/json" };

export const listarClientes = () => pedir<Tenant[]>("/tenants");

export const crearCliente = (datos: {
  slug: string;
  name: string;
  system_prompt: string;
}) => pedir<Tenant>("/tenants", { method: "POST", headers: json, body: JSON.stringify(datos) });

export const guardarPrompt = (id: string, system_prompt: string) =>
  pedir<Tenant>(`/tenants/${id}/prompt`, {
    method: "PATCH",
    headers: json,
    body: JSON.stringify({ system_prompt }),
  });

export const guardarLimite = (id: string, monthly_message_limit: number | null) =>
  pedir<Tenant>(`/tenants/${id}/limit`, {
    method: "PATCH",
    headers: json,
    body: JSON.stringify({ monthly_message_limit }),
  });

export const listarDocumentos = (id: string) => pedir<Documento[]>(`/tenants/${id}/documents`);

export const subirDocumento = (id: string, archivo: File) => {
  const form = new FormData();
  form.append("file", archivo);
  // Sin Content-Type a mano: fetch le pone el boundary del multipart.
  return pedir<Documento>(`/tenants/${id}/documents`, { method: "POST", body: form });
};

export const borrarDocumento = (id: string, docId: string) =>
  pedir<void>(`/tenants/${id}/documents/${docId}`, { method: "DELETE" });

export const verUso = (id: string) => pedir<Uso>(`/tenants/${id}/usage`);

export type WhatsApp = {
  phone_number_id: string | null;
  tiene_token: boolean;
  configurado: boolean;
};

export const verWhatsApp = (id: string) => pedir<WhatsApp>(`/tenants/${id}/whatsapp`);

/**
 * `access_token` en undefined deja el token guardado como esta; en "" lo borra.
 * Asi se puede corregir el numero sin tener que volver a pegar el token (que la
 * API no devuelve nunca).
 */
export const guardarWhatsApp = (
  id: string,
  datos: { phone_number_id?: string; access_token?: string },
) =>
  pedir<WhatsApp>(`/tenants/${id}/whatsapp`, {
    method: "PATCH",
    headers: json,
    body: JSON.stringify(datos),
  });

export type LinkOnboarding = { url: string; expira_at: string };

/**
 * Emite el link con el que el cliente conecta su WhatsApp solo, sin entrar al
 * panel ni tocar Business Manager. Se le manda por mail o WhatsApp.
 */
export const generarLinkOnboarding = (id: string) =>
  pedir<LinkOnboarding>(`/tenants/${id}/onboarding-link`, { method: "POST" });

export type Conversacion = {
  id: string;
  channel: string;
  /** El numero del usuario final en WhatsApp: con esto se lo busca en la bandeja de Meta. */
  external_id: string;
  last_activity_at: string;
  pausada_hasta: string | null;
  /**
   * ★ Estos tres los calcula la API. El panel no compara fechas: se renderiza
   * en el servidor (Railway, en UTC) y cualquier cuenta que hiciera aca daria
   * horas que no son las del usuario. Ademas leer el reloj durante el render
   * rompe la regla de pureza de React.
   */
  en_modo_manual: boolean;
  minutos_inactiva: number;
  minutos_restantes: number | null;
  mensajes: number;
  ultimo_mensaje: string | null;
};

export const listarConversaciones = (id: string) =>
  pedir<Conversacion[]>(`/tenants/${id}/conversations`);

/** Silencia al bot en esa conversacion por `horas`. Repetirlo corre el vencimiento. */
export const pausarBot = (id: string, conversacionId: string, horas: number) =>
  pedir<Conversacion>(`/tenants/${id}/conversations/${conversacionId}/manual`, {
    method: "POST",
    headers: json,
    body: JSON.stringify({ horas }),
  });

export const reanudarBot = (id: string, conversacionId: string) =>
  pedir<Conversacion>(`/tenants/${id}/conversations/${conversacionId}/manual`, {
    method: "DELETE",
  });

export const listarClaves = (id: string) => pedir<Clave[]>(`/tenants/${id}/keys`);

export const emitirClave = (id: string, name: string, scopes: string[]) =>
  pedir<ClaveCreada>(`/tenants/${id}/keys`, {
    method: "POST",
    headers: json,
    body: JSON.stringify({ name, scopes }),
  });

export const revocarClave = (id: string, keyId: string) =>
  pedir<void>(`/tenants/${id}/keys/${keyId}`, { method: "DELETE" });
