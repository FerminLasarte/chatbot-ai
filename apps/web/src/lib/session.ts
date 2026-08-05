import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

// ¿Por que una contrasena unica y no cuentas por persona?
//
// El panel lo usa la agencia, no los clientes finales. Para un equipo chico una
// contrasena compartida es proporcionada, y agregar usuarios despues no obliga a
// rehacer nada de esto: cambia que se guarda en la sesion, no como se firma.
//
// Lo que NO es negociable es que la clave admin de la API jamas llegue al
// navegador. Por eso el panel habla con la API solo desde el servidor (ver
// lib/api.ts) y el navegador nunca ve mas que esta cookie firmada.

const COOKIE = "panel_sesion";
const DURACION_MS = 12 * 60 * 60 * 1000; // 12 h

function secreto(): string {
  const s = process.env.PANEL_SECRET;
  if (!s) throw new Error("falta PANEL_SECRET");
  return s;
}

function firmar(payload: string): string {
  return createHmac("sha256", secreto()).update(payload).digest("base64url");
}

/** Compara en tiempo constante: un `===` filtra por cuanto tarda en fallar. */
function firmaValida(payload: string, firma: string): boolean {
  const esperada = Buffer.from(firmar(payload));
  const recibida = Buffer.from(firma);
  if (esperada.length !== recibida.length) return false;
  return timingSafeEqual(esperada, recibida);
}

export async function crearSesion(): Promise<void> {
  const expira = Date.now() + DURACION_MS;
  const payload = Buffer.from(JSON.stringify({ exp: expira })).toString("base64url");
  const token = `${payload}.${firmar(payload)}`;

  (await cookies()).set(COOKIE, token, {
    httpOnly: true, // el JavaScript de la pagina no puede leerla
    secure: process.env.NODE_ENV === "production", // en local no hay https
    sameSite: "lax",
    path: "/",
    expires: new Date(expira),
  });
}

export async function cerrarSesion(): Promise<void> {
  (await cookies()).delete(COOKIE);
}

export async function haySesion(): Promise<boolean> {
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) return false;

  const [payload, firma] = token.split(".");
  if (!payload || !firma || !firmaValida(payload, firma)) return false;

  try {
    const { exp } = JSON.parse(Buffer.from(payload, "base64url").toString());
    return typeof exp === "number" && Date.now() < exp;
  } catch {
    return false;
  }
}

/** Compara la contrasena tambien en tiempo constante. */
export function passwordCorrecta(intento: string): boolean {
  const real = process.env.PANEL_PASSWORD;
  if (!real) throw new Error("falta PANEL_PASSWORD");

  const a = Buffer.from(intento);
  const b = Buffer.from(real);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}
