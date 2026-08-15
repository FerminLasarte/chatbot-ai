"use server";

import { revalidatePath } from "next/cache";

import { AccesoRevocado, pausarMiBot, reanudarMiBot } from "@/lib/portal";
import { claveDelPortal } from "@/lib/sesion-portal";

export type EstadoPortal = { error?: string; ok?: string };

/**
 * ★ ESTAS ACCIONES NO LLAMAN A `exigirSesion()`, Y TAMPOCO SON PUBLICAS.
 *
 * Las de panel/acciones.ts exigen la sesion de la agencia porque operan sobre
 * cualquier cliente. Estas usan otra credencial: la clave `client_portal` que
 * vive en la cookie del cliente. Sin cookie no hay clave y no hay a quien
 * pedirle nada, asi que la accion corta sola.
 *
 * ★ LO QUE SOSTIENE EL AISLAMIENTO
 * La clave sale SIEMPRE de la cookie, nunca del formulario. Una Server Action
 * es un endpoint HTTP: cualquiera puede mandarle el FormData que quiera. Si la
 * clave (o un tenantId) viniera en un campo del form, alcanzaria con cambiarlo
 * para operar en nombre de otro negocio. Lo unico que se acepta de afuera es el
 * id de la conversacion, y ese la API lo valida contra el tenant de la clave:
 * un id ajeno da 404 (ver services/conversaciones.py).
 */
const SIN_ACCESO = "Se te vencio el acceso. Volve a entrar con el link que te pasaron.";

export async function pausarBot(_estado: EstadoPortal, form: FormData): Promise<EstadoPortal> {
  const clave = await claveDelPortal();
  if (!clave) return { error: SIN_ACCESO };

  const conversacionId = String(form.get("conversacion_id") ?? "");
  const horas = Number(form.get("horas") ?? "");

  // El mismo tope que valida la API: no hay pausa indefinida, justamente para
  // que un olvido no deje al negocio sin bot para siempre.
  if (!Number.isInteger(horas) || horas < 1 || horas > 168) {
    return { error: "Elegi por cuanto tiempo pausar el bot." };
  }

  try {
    await pausarMiBot(clave, conversacionId, horas);
  } catch (e) {
    if (e instanceof AccesoRevocado) return { error: SIN_ACCESO };
    return { error: e instanceof Error ? e.message : "No se pudo pausar." };
  }

  revalidatePath("/mi-negocio");
  return { ok: `Listo: el bot no contesta por ${horas} h. Contestale vos desde WhatsApp.` };
}

export async function reanudarBot(_estado: EstadoPortal, form: FormData): Promise<EstadoPortal> {
  const clave = await claveDelPortal();
  if (!clave) return { error: SIN_ACCESO };

  const conversacionId = String(form.get("conversacion_id") ?? "");

  try {
    await reanudarMiBot(clave, conversacionId);
  } catch (e) {
    if (e instanceof AccesoRevocado) return { error: SIN_ACCESO };
    return { error: e instanceof Error ? e.message : "No se pudo reactivar." };
  }

  revalidatePath("/mi-negocio");
  return { ok: "El bot vuelve a responder en esta conversacion." };
}
