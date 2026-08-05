import { redirect } from "next/navigation";

import { haySesion } from "@/lib/session";
import { entrar } from "../acciones";
import { Boton, Formulario, claseInput } from "../ui";

export const metadata = { title: "Panel — ingresar" };

export default async function Login() {
  if (await haySesion()) redirect("/panel");

  return (
    <div className="flex flex-1 items-center justify-center bg-zinc-50 px-4 py-10 dark:bg-black">
      <div className="w-full max-w-sm rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Panel de administraci&oacute;n
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Acceso solo para el equipo.
        </p>

        <Formulario accion={entrar} className="mt-5 flex flex-col gap-3">
          <input
            type="password"
            name="password"
            placeholder="Contrase&ntilde;a"
            autoComplete="current-password"
            required
            className={claseInput}
          />
          <Boton>Entrar</Boton>
        </Formulario>
      </div>
    </div>
  );
}
