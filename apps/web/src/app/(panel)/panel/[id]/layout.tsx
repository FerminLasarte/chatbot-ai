import Link from "next/link";
import { notFound } from "next/navigation";

import { Chip } from "@/components/ui";
import { listarClaves, verWhatsApp } from "@/lib/api";
import { clienteDelPanel, exigirPanel } from "../guardia";
import { NavDelCliente } from "./nav";

export const metadata = { title: "Cliente" };

/**
 * El marco de un cliente: quien es, en que estado esta, y a que seccion se va.
 *
 * ★ POR QUE UNA BARRA PEGADA AL BORDE Y NO UNA COLUMNA CENTRADA
 * Esto se mira todo el dia en un monitor grande. Con el contenido encerrado en
 * una columna angosta, dos tercios de la pantalla quedaban en blanco y la
 * navegacion flotaba como texto suelto en el medio de la nada. Una barra con
 * cuerpo propio contra el borde da el limite que el ojo necesita para leer la
 * pantalla como una herramienta y no como un formulario.
 *
 * ★ POR QUE EL ESTADO VIVE ACA
 * "Tiene WhatsApp conectado" y "el duenio tiene acceso" son cosas que hay que
 * saber SIEMPRE, en cualquier seccion. Estaban escondidas adentro de la seccion
 * que las administra, asi que para saber si el bot podia contestar habia que ir
 * a mirar. Ademas el layout no se vuelve a renderizar al cambiar de seccion:
 * estas dos consultas se hacen una vez por cliente, no una por pantalla.
 */
export default async function LayoutDelCliente({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  await exigirPanel();
  const { id } = await params;

  const [cliente, wa, claves] = await Promise.all([
    clienteDelPanel(id),
    verWhatsApp(id),
    listarClaves(id),
  ]);
  if (!cliente) notFound();

  const tienePortal = claves.some((k) => k.is_active && k.scopes.includes("client_portal"));

  return (
    <div className="flex flex-1 flex-col lg:flex-row">
      <aside className="border-borde bg-superficie lg:sticky lg:top-0 lg:h-screen lg:w-60 lg:shrink-0 lg:border-r">
        <div className="flex flex-col gap-5 px-4 py-5 lg:px-5 lg:py-6">
          <div>
            <Link
              href="/panel"
              className="text-xs text-texto-tenue transition-colors hover:text-texto"
            >
              &larr; Clientes
            </Link>
            <h1 className="mt-2 truncate text-lg font-semibold tracking-tight text-texto">
              {cliente.name}
            </h1>
            <p className="truncate text-xs text-texto-tenue">{cliente.slug}</p>
          </div>

          <NavDelCliente id={id} />
        </div>
      </aside>

      <main className="min-w-0 flex-1 px-4 py-6 lg:px-8 lg:py-8">
        <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6">
          <EstadoDelCliente
            configurado={wa.configurado}
            tienePortal={tienePortal}
            activo={cliente.is_active}
          />
          {children}
        </div>
      </main>
    </div>
  );
}

/** Lo que hay que saber de este cliente en cualquier seccion. */
function EstadoDelCliente({
  configurado,
  tienePortal,
  activo,
}: {
  configurado: boolean;
  tienePortal: boolean;
  activo: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Chip tono={configurado ? "ok" : "alerta"}>
        {configurado ? "WhatsApp conectado" : "WhatsApp sin configurar"}
      </Chip>
      <Chip tono={tienePortal ? "neutro" : "alerta"}>
        {tienePortal ? "El dueño tiene acceso" : "El dueño no tiene acceso"}
      </Chip>
      {!activo && <Chip tono="alerta">Cliente inactivo</Chip>}
    </div>
  );
}
