"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import * as api from "@/lib/api";
import { cerrarSesion, crearSesion, haySesion, passwordCorrecta } from "@/lib/session";

export type Estado = { error?: string; ok?: string; clave?: string };

/**
 * ★ Toda accion que toque datos pasa por aca primero.
 *
 * Las Server Actions son endpoints HTTP: quedan expuestas aunque la pagina que
 * las usa este detras del login. Sin esta comprobacion, cualquiera podria
 * invocarlas directamente y operar sobre los clientes sin haber entrado nunca
 * al panel. No alcanza con esconder la UI.
 */
async function exigirSesion(): Promise<void> {
  if (!(await haySesion())) redirect("/panel/login");
}

// --- Sesion ---

export async function entrar(_estado: Estado, form: FormData): Promise<Estado> {
  const password = String(form.get("password") ?? "");
  if (!passwordCorrecta(password)) {
    // Espera fija: hace mas lento probar contrasenas a mano alzada.
    await new Promise((r) => setTimeout(r, 700));
    return { error: "Contrasena incorrecta." };
  }
  await crearSesion();
  redirect("/panel");
}

export async function salir(): Promise<void> {
  await cerrarSesion();
  redirect("/panel/login");
}

// --- Clientes ---

export async function nuevoCliente(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();

  const name = String(form.get("name") ?? "").trim();
  const slug = String(form.get("slug") ?? "").trim();
  const system_prompt = String(form.get("system_prompt") ?? "").trim();

  if (!name || !slug) return { error: "El nombre y el identificador son obligatorios." };
  if (!/^[a-z0-9-]+$/.test(slug)) {
    return { error: "El identificador solo admite minusculas, numeros y guiones." };
  }

  try {
    await api.crearCliente({ slug, name, system_prompt });
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo crear" };
  }

  revalidatePath("/panel");
  redirect("/panel");
}

export async function guardarPrompt(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();
  const id = String(form.get("id") ?? "");
  const system_prompt = String(form.get("system_prompt") ?? "");

  try {
    await api.guardarPrompt(id, system_prompt);
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo guardar" };
  }
  revalidatePath(`/panel/${id}`);
  return { ok: "Comportamiento guardado." };
}

export async function guardarLimite(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();
  const id = String(form.get("id") ?? "");
  const crudo = String(form.get("monthly_message_limit") ?? "").trim();
  const limite = crudo === "" ? null : Number(crudo);

  if (limite !== null && (!Number.isInteger(limite) || limite < 0)) {
    return { error: "El tope tiene que ser un numero entero, o vacio para sin limite." };
  }

  try {
    await api.guardarLimite(id, limite);
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo guardar" };
  }
  revalidatePath(`/panel/${id}`);
  return { ok: "Tope actualizado." };
}

// --- Documentos ---

export async function subirDocumento(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();
  const id = String(form.get("id") ?? "");
  const archivo = form.get("file");

  if (!(archivo instanceof File) || archivo.size === 0) {
    return { error: "Elegi un archivo." };
  }

  try {
    const doc = await api.subirDocumento(id, archivo);
    revalidatePath(`/panel/${id}`);
    return { ok: `"${doc.title}" cargado en ${doc.chunks} fragmentos.` };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo subir" };
  }
}

export async function borrarDocumento(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();
  const id = String(form.get("id") ?? "");
  const docId = String(form.get("doc_id") ?? "");

  try {
    await api.borrarDocumento(id, docId);
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo borrar" };
  }
  revalidatePath(`/panel/${id}`);
  return { ok: "Documento eliminado." };
}

// --- WhatsApp ---

export async function guardarWhatsApp(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();
  const id = String(form.get("id") ?? "");
  const phone_number_id = String(form.get("phone_number_id") ?? "").trim();
  const token = String(form.get("access_token") ?? "").trim();

  // El campo del token viene vacio cuando no se quiso cambiar: se omite para
  // que el backend conserve el que ya estaba (no lo devuelve nunca, asi que no
  // se puede recargar en el formulario).
  const datos: { phone_number_id?: string; access_token?: string } = { phone_number_id };
  if (token) datos.access_token = token;

  try {
    await api.guardarWhatsApp(id, datos);
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo guardar" };
  }
  revalidatePath(`/panel/${id}`);
  return { ok: "WhatsApp actualizado." };
}

export async function borrarTokenWhatsApp(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();
  const id = String(form.get("id") ?? "");
  try {
    await api.guardarWhatsApp(id, { access_token: "" });
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo borrar" };
  }
  revalidatePath(`/panel/${id}`);
  return { ok: "Token eliminado." };
}

// --- Modo manual ---

export async function pausarBot(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();
  const id = String(form.get("id") ?? "");
  const conversacionId = String(form.get("conversacion_id") ?? "");
  const horas = Number(form.get("horas") ?? "");

  // El tope de una semana es el mismo que valida la API: no hay pausa
  // indefinida, justamente para que un olvido no silencie al bot para siempre.
  if (!Number.isInteger(horas) || horas < 1 || horas > 168) {
    return { error: "Elegi por cuanto tiempo pausar el bot." };
  }

  try {
    await api.pausarBot(id, conversacionId, horas);
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo pausar" };
  }
  revalidatePath(`/panel/${id}`);
  return { ok: `Bot pausado ${horas} h. Contesta vos desde Meta Business Suite.` };
}

export async function reanudarBot(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();
  const id = String(form.get("id") ?? "");
  const conversacionId = String(form.get("conversacion_id") ?? "");

  try {
    await api.reanudarBot(id, conversacionId);
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo reactivar" };
  }
  revalidatePath(`/panel/${id}`);
  return { ok: "El bot vuelve a responder en esta conversacion." };
}

// --- Claves ---

export async function emitirClave(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();
  const id = String(form.get("id") ?? "");
  const name = String(form.get("name") ?? "").trim() || "clave";
  const scope = String(form.get("scope") ?? "chat");

  try {
    const creada = await api.emitirClave(id, name, [scope]);
    revalidatePath(`/panel/${id}`);
    return { clave: creada.api_key, ok: "Clave creada. Copiala: no se vuelve a mostrar." };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo emitir" };
  }
}

export async function revocarClave(_estado: Estado, form: FormData): Promise<Estado> {
  await exigirSesion();
  const id = String(form.get("id") ?? "");
  const keyId = String(form.get("key_id") ?? "");

  try {
    await api.revocarClave(id, keyId);
  } catch (e) {
    return { error: e instanceof Error ? e.message : "no se pudo revocar" };
  }
  revalidatePath(`/panel/${id}`);
  return { ok: "Clave revocada." };
}
