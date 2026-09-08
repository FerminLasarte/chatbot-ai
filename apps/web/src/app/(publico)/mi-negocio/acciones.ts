"use server";

import { revalidatePath } from "next/cache";

import {
  AccesoRevocado,
  guardarMiFicha as guardarFichaEnLaApi,
  pausarMiBot,
  reanudarMiBot,
  responderYoMismo,
  verMiConversacion,
  type MensajeDelHilo,
} from "@/lib/portal";
import { fichaDesdeFormulario } from "@/lib/ficha";
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


/** Lo que el navegador recibe al abrir una conversacion: el hilo, o un motivo. */
export type HiloCargado = { mensajes?: MensajeDelHilo[]; error?: string };

/**
 * El hilo de una conversacion, para el panel que se abre al tocarla.
 *
 * ★ Se pide al abrir y no junto con la lista a proposito. Traer todos los
 * mensajes de todas las conversaciones para mostrar una es tirar a la basura la
 * mayoria, y en un negocio con meses de historial eso se nota. Ademas la
 * credencial vive en la cookie y nunca viaja al navegador: la unica forma de
 * pedir un hilo desde el cliente es esta accion, que la resuelve del lado del
 * servidor y valida contra la API que la conversacion sea de este negocio.
 */
export async function traerMiHilo(conversacionId: string): Promise<HiloCargado> {
  const clave = await claveDelPortal();
  if (!clave) return { error: SIN_ACCESO };

  try {
    return { mensajes: await verMiConversacion(clave, conversacionId) };
  } catch (e) {
    if (e instanceof AccesoRevocado) return { error: SIN_ACCESO };
    return { error: "No pudimos abrir esta conversacion. Proba de nuevo en un rato." };
  }
}

/** Lo que el navegador recibe al mandar una respuesta: el mensaje, o un motivo. */
export type RespuestaEnviada = { mensaje?: MensajeDelHilo; error?: string };

/**
 * El duenio del negocio le contesta a su cliente sin salir del portal.
 *
 * ★ El error de la API se devuelve tal cual. Los motivos por los que un envio
 * no sale ya vienen redactados para que los lea alguien no tecnico -que
 * pasaron las 24 h, que falta conectar el WhatsApp- y cada uno dice algo
 * distinto que hacer. Un generico "no se pudo enviar" lo deja sin saber si
 * conviene reintentar o esperar a que el cliente escriba.
 */
export async function responderYo(
  conversacionId: string,
  texto: string,
): Promise<RespuestaEnviada> {
  const clave = await claveDelPortal();
  if (!clave) return { error: SIN_ACCESO };

  const limpio = texto.trim();
  if (!limpio) return { error: "Escribi algo antes de mandar." };

  try {
    const mensaje = await responderYoMismo(clave, conversacionId, limpio);
    // La conversacion queda pausada y sin pedido pendiente: la lista de atras
    // tiene que reflejarlo sin que nadie recargue.
    revalidatePath("/mi-negocio");
    return { mensaje };
  } catch (e) {
    if (e instanceof AccesoRevocado) return { error: SIN_ACCESO };
    return { error: e instanceof Error ? e.message : "No se pudo enviar el mensaje." };
  }
}


/**
 * Guarda la ficha del negocio.
 *
 * La clave sale de la cookie, como todas las de este archivo: lo unico que se
 * acepta del formulario son los campos de la ficha, y la API los valida antes
 * de escribirlos (ver `app/schemas/negocio.py`). Un 422 vuelve como texto para
 * que el duenio pueda arreglarlo, no como un error tecnico.
 */
export async function guardarMiFicha(
  _estado: EstadoPortal,
  form: FormData,
): Promise<EstadoPortal> {
  const clave = await claveDelPortal();
  if (!clave) return { error: SIN_ACCESO };

  try {
    await guardarFichaEnLaApi(clave, fichaDesdeFormulario(form));
  } catch (e) {
    if (e instanceof AccesoRevocado) return { error: SIN_ACCESO };
    return { error: e instanceof Error ? e.message : "No se pudieron guardar los datos." };
  }

  revalidatePath("/mi-negocio/datos");
  return { ok: "Listo. Tu asistente ya contesta con estos datos." };
}
