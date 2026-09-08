import { redirect } from "next/navigation";

import { InterruptorDeTema } from "@/components/tema";
import { claseCampo } from "@/components/ui";
import { haySesion } from "@/lib/session";
import { entrar } from "../acciones";
import { Boton, Formulario } from "../ui";

export const metadata = { title: "Ingresar" };

// La puerta del panel.
//
// ★ No lleva la barra del panel (ver marco.tsx): esa barra muestra "Salir" y
// las secciones de un cliente, y aca todavia no entro nadie. Lo unico que
// comparte con el resto es el interruptor de tema, porque alguien que trabaja
// en oscuro tiene que poder ponerlo antes de entrar y no despues.

export default async function Login() {
  if (await haySesion()) redirect("/panel");

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between px-4 py-3 lg:px-6">
        <span className="flex items-baseline gap-2 text-sm font-semibold tracking-tight text-texto">
          ArgencoreAI
          <span className="text-[11px] font-normal text-texto-tenue">Panel</span>
        </span>
        <InterruptorDeTema />
      </header>

      <main className="flex flex-1 items-center justify-center px-4 pb-24">
        <div className="w-full max-w-sm rounded-panel border border-borde bg-superficie p-6 shadow-panel">
          <h1 className="font-titulo text-lg font-semibold tracking-tight text-texto">
            Panel de administraci&oacute;n
          </h1>
          <p className="mt-1 text-sm text-texto-suave">
            Desde ac&aacute; se ven las conversaciones de todos los clientes. Es solo para el
            equipo.
          </p>

          <Formulario accion={entrar} className="mt-6 flex flex-col gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-texto">Contrase&ntilde;a</span>
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                required
                autoFocus
                className={claseCampo}
              />
            </label>
            <div className="mt-1 grid">
              <Boton>Entrar</Boton>
            </div>
          </Formulario>
        </div>
      </main>
    </div>
  );
}
