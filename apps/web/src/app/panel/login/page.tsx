import { redirect } from "next/navigation";

import { haySesion } from "@/lib/session";
import { entrar } from "../acciones";
import { Boton, Formulario } from "../ui";
import { claseCampo } from "@/components/ui";

export const metadata = { title: "Panel — ingresar" };

export default async function Login() {
  if (await haySesion()) redirect("/panel");

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm rounded-xl border border-borde bg-superficie p-6">
        <h1 className="text-lg font-semibold text-texto">
          Panel de administraci&oacute;n
        </h1>
        <p className="mt-1 text-sm text-texto-suave">
          Acceso solo para el equipo.
        </p>

        <Formulario accion={entrar} className="mt-5 flex flex-col gap-3">
          <input
            type="password"
            name="password"
            placeholder="Contrase&ntilde;a"
            autoComplete="current-password"
            required
            className={claseCampo}
          />
          <Boton>Entrar</Boton>
        </Formulario>
      </div>
    </div>
  );
}
