"use server";

import { conectarWhatsAppDelCliente, ErrorOnboarding } from "@/lib/onboarding";

export type EstadoConexion = {
  error?: string;
  ok?: string;
  advertencia?: string;
};

/**
 * Termina el alta con lo que devolvio el popup de Facebook.
 *
 * ★ ESTA ACCION NO LLAMA A `exigirSesion()`, Y ESTA BIEN ASI.
 *
 * Las de panel/acciones.ts si lo hacen porque operan sobre cualquier cliente y
 * quien las invoca tiene que haber entrado al panel. Esta es al reves: la usa el
 * cliente de la agencia, que por diseno no tiene usuario. Su credencial es el
 * `token` del link, que la API valida en cada llamada (firma + vencimiento) y
 * que ademas fija sobre QUE cliente se puede operar. Poner un chequeo de sesion
 * aca romperia el flujo entero sin agregar seguridad.
 *
 * Lo que si hay que sostener: que este archivo no exporte nunca nada que opere
 * sobre un cliente distinto del que dice el token.
 */
export async function conectarWhatsApp(
  token: string,
  datos: { code: string; waba_id: string; phone_number_id: string },
): Promise<EstadoConexion> {
  try {
    const r = await conectarWhatsAppDelCliente(token, datos);
    return {
      ok: "Listo, tu WhatsApp quedo conectado.",
      advertencia: r.advertencia ?? undefined,
    };
  } catch (e) {
    if (e instanceof ErrorOnboarding) return { error: e.message };
    return { error: "No se pudo completar la conexion. Proba de nuevo." };
  }
}
