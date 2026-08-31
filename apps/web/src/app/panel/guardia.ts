import "server-only";

import { redirect } from "next/navigation";

import { listarClientes, type Tenant } from "@/lib/api";
import { haySesion } from "@/lib/session";

/**
 * Toda pagina del panel empieza por aca.
 *
 * ★ El chequeo se repite en cada pagina y no queda solo en el layout a
 * proposito: un layout de Next no es una barrera de seguridad -las paginas
 * hijas se renderizan igual- y esconder la UI nunca alcanzo. Las Server Actions
 * tienen su propio `exigirSesion()` por la misma razon.
 */
export async function exigirPanel(): Promise<void> {
  if (!(await haySesion())) redirect("/panel/login");
}

/** El cliente de esta seccion, o 404.
 *
 *  La API no tiene un GET de un cliente suelto: se filtra la lista, que es
 *  corta y ya viene cacheada por el fetch de la peticion. */
export async function clienteDelPanel(id: string): Promise<Tenant | undefined> {
  const clientes = await listarClientes();
  return clientes.find((c) => c.id === id);
}
