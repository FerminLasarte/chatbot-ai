import Link from "next/link";
import { notFound } from "next/navigation";

import { clienteDelPanel, exigirPanel } from "../guardia";
import { NavDelCliente } from "./nav";

export const metadata = { title: "Cliente" };

/**
 * El marco de un cliente: quien es, a que seccion se va, y el contenido.
 *
 * ★ POR QUE SECCIONES Y NO UNA PAGINA LARGA
 * Antes todo esto era un solo archivo de 478 lineas que pedia SIETE cosas a la
 * API en cada visita -conversaciones, documentos, claves, uso, incidentes,
 * WhatsApp, clientes- para mostrarlas apiladas con el mismo peso. Ahora cada
 * seccion es una ruta: se lleva solo sus datos, tiene su propia URL para
 * mandarle a alguien, y el archivo entra en una pantalla.
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

  const cliente = await clienteDelPanel(id);
  if (!cliente) notFound();

  return (
    <div className="flex-1 px-4 py-8 sm:py-10">
      <div className="mx-auto w-full max-w-5xl">
        <header className="mb-6">
          <Link
            href="/panel"
            className="text-sm text-texto-suave transition-colors hover:text-texto"
          >
            &larr; Clientes
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-texto">
            {cliente.name}
          </h1>
          <p className="text-sm text-texto-tenue">{cliente.slug}</p>
        </header>

        {/* En pantalla ancha la navegacion va al costado y queda fija mientras
            se scrollea la seccion; en un telefono pasa a ser una fila arriba,
            que es donde alguien la busca. */}
        <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
          <aside className="lg:w-48 lg:shrink-0">
            <div className="lg:sticky lg:top-8">
              <NavDelCliente id={id} />
            </div>
          </aside>
          <main className="flex min-w-0 flex-1 flex-col gap-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
