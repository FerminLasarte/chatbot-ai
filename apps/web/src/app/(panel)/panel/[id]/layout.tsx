import Link from "next/link";
import { notFound } from "next/navigation";

import { IconoFlechaIzquierda } from "@/components/iconos";
import { Chip } from "@/components/ui";
import { listarClaves, verWhatsApp } from "@/lib/api";
import { clienteDelPanel, exigirPanel } from "../guardia";
import { BarraDelPanel } from "../marco";
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
 *
 * ★ POR QUE EL NOMBRE DEL CLIENTE ESTA EN LA BARRA Y NO EN LA COLUMNA
 * Es la respuesta a "¿en cual de los seis estoy parado?", y esa pregunta
 * aparece justo cuando alguien vuelve a la pestania despues de un rato. Arriba
 * de todo se contesta sin mover los ojos.
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
    <>
      <BarraDelPanel>
        <div className="flex min-w-0 items-center gap-2">
          <Link
            href="/panel"
            aria-label="Volver a clientes"
            className="rounded-control p-1 text-texto-tenue transition-colors hover:bg-superficie-2 hover:text-texto"
          >
            <IconoFlechaIzquierda className="size-3.5" />
          </Link>
          <span className="truncate text-sm font-medium text-texto">{cliente.name}</span>
          <span className="tabular hidden font-mono text-[11px] text-texto-tenue sm:inline">
            {cliente.slug}
          </span>

          <span className="ml-2 hidden items-center gap-1.5 md:flex">
            {!wa.configurado && <Chip tono="alerta">WhatsApp sin conectar</Chip>}
            {!tienePortal && <Chip tono="neutro">Sin acceso del dueño</Chip>}
            {!cliente.is_active && <Chip tono="alerta">Inactivo</Chip>}
            {wa.configurado && tienePortal && cliente.is_active && (
              <Chip tono="ok">Todo conectado</Chip>
            )}
          </span>
        </div>
      </BarraDelPanel>

      <div className="flex flex-1 flex-col lg:flex-row">
        <aside className="border-borde bg-superficie lg:sticky lg:top-12 lg:h-[calc(100dvh-3rem)] lg:w-52 lg:shrink-0 lg:border-r">
          <div className="px-3 py-3 lg:px-3 lg:py-4">
            <NavDelCliente id={id} />
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-6 lg:px-6 lg:py-8">
          <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-6">{children}</div>
        </main>
      </div>
    </>
  );
}
