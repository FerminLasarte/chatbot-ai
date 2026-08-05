import Link from "next/link";
import { redirect } from "next/navigation";

import { ErrorApi, listarClientes } from "@/lib/api";
import { haySesion } from "@/lib/session";
import { nuevoCliente, salir } from "./acciones";
import { Boton, Formulario, claseInput } from "./ui";

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

  return (
    <Marco>
      <section className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        {clientes.length === 0 ? (
          <p className="p-6 text-center text-sm text-zinc-500">
            Todav&iacute;a no hay clientes. Cre&aacute; el primero abajo.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {clientes.map((c) => (
              <li key={c.id}>
                <Link
                  href={`/panel/${c.id}`}
                  className="flex items-center justify-between gap-4 p-4 hover:bg-zinc-50 dark:hover:bg-zinc-800"
                >
                  <span>
                    <span className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                      {c.name}
                    </span>
                    <span className="block text-xs text-zinc-500">{c.slug}</span>
                  </span>
                  <span className="text-xs text-zinc-400">
                    {c.is_active ? "activo" : "inactivo"} &rarr;
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Nuevo cliente</h2>

        <Formulario accion={nuevoCliente} className="mt-4 flex flex-col gap-3">
          <label className="block text-xs text-zinc-500">
            Nombre del negocio
            <input name="name" required placeholder="Caba&ntilde;as Altos de la Sierra"
              className={`mt-1 ${claseInput}`} />
          </label>

          <label className="block text-xs text-zinc-500">
            Identificador (min&uacute;sculas, sin espacios)
            <input name="slug" required placeholder="cabanas-altos" className={`mt-1 ${claseInput}`} />
          </label>

          <label className="block text-xs text-zinc-500">
            C&oacute;mo se tiene que comportar
            <textarea
              name="system_prompt"
              rows={4}
              placeholder="Sos el asistente de Caba&ntilde;as Altos de la Sierra. Tono cordial. No inventes precios ni disponibilidad; si no sabes algo, ofrece pasar el contacto de recepcion."
              className={`mt-1 ${claseInput}`}
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
    <div className="flex-1 bg-zinc-50 px-4 py-10 dark:bg-black">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Clientes</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Cada cliente tiene su comportamiento y sus documentos.
            </p>
          </div>
          <form action={salir}>
            <button
              type="submit"
              className="text-sm text-zinc-500 underline underline-offset-4 hover:text-zinc-800 dark:hover:text-zinc-200"
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
