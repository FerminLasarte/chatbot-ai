import "server-only";

import { cookies } from "next/headers";

// La sesion del portal del cliente. NO se reusa `panel_sesion` (lib/session.ts).
//
// ★ Esa cookie significa "entre con la contrasena de la agencia" y habilita a
// ver TODOS los clientes. Esta significa "soy el duenio de este negocio". Si
// fueran la misma cookie, cualquier error al leerla dejaria a un cliente
// mirando el panel entero —y al reves, una sesion de agencia caducada podria
// terminar operando como un cliente cualquiera—. Son dos poblaciones distintas
// de usuarios: comparten navegador y nada mas.
//
// ★ Que guarda: la clave `client_portal` tal cual. No hace falta firmarla
// -como si hace panel_sesion, que guarda datos que nos inventamos nosotros-
// porque esta cookie no afirma nada: es un secreto que la API verifica contra
// el hash guardado en cada peticion. Una cookie manipulada no se convierte en
// otro cliente, se convierte en un 401.
//
// La contra de guardar el secreto en la cookie es que hay que tratarla como
// tal: httpOnly (el JS de la pagina no la lee), secure en produccion, y
// sameSite lax.

const COOKIE = "portal_sesion";

// Larga a proposito: esto reemplaza a un login. Si venciera en horas, el
// cliente tendria que volver a buscar el link en el chat cada vez, y la
// respuesta previsible a esa friccion es que la agencia le mande links nuevos
// todo el tiempo. La caducidad real de este acceso es la revocacion, que es
// inmediata y no depende de esperar a que algo venza.
const DURACION_DIAS = 180;

export async function guardarClaveDelPortal(clave: string): Promise<void> {
  (await cookies()).set(COOKIE, clave, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production", // en local no hay https
    sameSite: "lax",
    path: "/",
    maxAge: DURACION_DIAS * 24 * 60 * 60,
  });
}

export async function olvidarClaveDelPortal(): Promise<void> {
  (await cookies()).delete(COOKIE);
}

/** La clave del cliente que esta mirando, o null si no entro por un link. */
export async function claveDelPortal(): Promise<string | null> {
  return (await cookies()).get(COOKIE)?.value ?? null;
}
