import Link from "next/link";
import { redirect } from "next/navigation";

import { ErrorApi, listarClientes, listarIncidentes } from "@/lib/api";
import { haySesion } from "@/lib/session";
import { nuevoCliente, salir } from "./acciones";
import { Boton, Formulario } from "./ui";
import { claseCampo } from "@/components/ui";

export const metadata = { title: "Panel — clientes" };

export default async function Panel() {
  if (!(await haySesion())) redirect("/panel/login");

  let clientes;
  try {
    clientes = await listarClientes();
  } catch (e) {
    return (
      <Marco>
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          No se pudo leer la lista de clientes:{" "}
          {e instanceof ErrorApi ? e.message : "error inesperado"}
        </p>
      </Marco>
    );
  }

  // Cuantos mensajes quedaron sin contestar, por cliente. Va aparte del try de
  // arriba a proposito: que el monitoreo falle no puede dejarte sin panel.
  const rotos = new Map<string, number>();
  try {
    for (const i of await listarIncidentes()) {
      if (i.tenant_id) rotos.set(i.tenant_id, (rotos.get(i.tenant_id) ?? 0) + 1);
    }
  } catch {
    /* si no se pueden leer, la lista se muestra igual */
  }
  const totalRotos = [...rotos.values()].reduce((a, b) => a + b, 0);

  return (
    <Marco>
      {totalRotos > 0 && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          <strong>
            {totalRotos} {totalRotos === 1 ? "mensaje quedo" : "mensajes quedaron"} sin
            contestar
          </strong>{" "}
          en {rotos.size} {rotos.size === 1 ? "cliente" : "clientes"}. Entr&aacute; al cliente
          marcado para ver el detalle.
        </p>
      )}

      <section className="overflow-hidden rounded-xl border border-borde bg-superficie">
        {clientes.length === 0 ? (
          <p className="p-6 text-center text-sm text-texto-suave">
            Todav&iacute;a no hay clientes. Cre&aacute; el primero abajo.
          </p>
        ) : (
          <ul className="divide-y divide-borde">
            {clientes.map((c) => (
              <li key={c.id}>
                <Link
                  href={`/panel/${c.id}`}
                  className="flex items-center justify-between gap-4 p-4 transition-colors hover:bg-superficie-2"
                >
                  <span>
                    <span className="block text-sm font-medium text-texto">
                      {c.name}
                    </span>
                    <span className="block text-xs text-texto-tenue">{c.slug}</span>
                  </span>
                  <span className="flex items-center gap-3 text-xs text-texto-tenue">
                    {rotos.has(c.id) && (
                      <span className="rounded-full bg-error-suave px-2 py-0.5 font-medium text-error">
                        {rotos.get(c.id)} sin contestar
                      </span>
                    )}
                    <span>
                      {c.is_active ? "activo" : "inactivo"} &rarr;
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-borde bg-superficie p-5">
        <h2 className="text-sm font-semibold text-texto">Nuevo cliente</h2>

        <Formulario accion={nuevoCliente} className="mt-4 flex flex-col gap-3">
          <label className="block text-xs text-texto-suave">
            Nombre del negocio
            <input name="name" required placeholder="Caba&ntilde;as Altos de la Sierra"
              className={`mt-1 ${claseCampo}`} />
          </label>

          <label className="block text-xs text-texto-suave">
            Identificador (min&uacute;sculas, sin espacios)
            <input name="slug" required placeholder="cabanas-altos" className={`mt-1 ${claseCampo}`} />
          </label>

          <label className="block text-xs text-texto-suave">
            C&oacute;mo se tiene que comportar
            <textarea
              name="system_prompt"
              rows={4}
              placeholder="Sos el asistente de Caba&ntilde;as Altos de la Sierra. Tono cordial. No inventes precios ni disponibilidad; si no sabes algo, ofrece pasar el contacto de recepcion."
              className={`mt-1 ${claseCampo}`}
            />
          </label>

          <div>
            <Boton>Crear cliente</Boton>
          </div>
        </Formulario>
      </section>
    </Marco>
  );
}

function Marco({ children }: { children: React.ReactNode }) {
  // flex-1, no min-h-full: el body es flex-col, asi que el hijo tiene que
  // crecer para llenar la pantalla. Con min-h-full queda una franja sin fondo.
  return (
    <div className="flex-1 px-4 py-10">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-texto">Clientes</h1>
            <p className="text-sm text-texto-suave">
              Cada cliente tiene su comportamiento y sus documentos.
            </p>
          </div>
          <form action={salir}>
            <button
              type="submit"
              className="text-sm text-texto-suave transition-colors hover:text-texto"
            >
              Salir
            </button>
          </form>
        </header>
        {children}
      </div>
    </div>
  );
}
