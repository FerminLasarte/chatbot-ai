import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { listarClaves, listarClientes, listarDocumentos, verUso } from "@/lib/api";
import { haySesion } from "@/lib/session";
import {
  borrarDocumento,
  emitirClave,
  guardarLimite,
  guardarPrompt,
  revocarClave,
  subirDocumento,
} from "../acciones";
import { Boton, Formulario, FormularioClave } from "../ui";
import { claseInput } from "@/lib/estilos";

export const metadata = { title: "Panel — cliente" };

export default async function Cliente({ params }: { params: Promise<{ id: string }> }) {
  if (!(await haySesion())) redirect("/panel/login");

  const { id } = await params;

  // Se piden en paralelo: son cuatro consultas independientes y en serie
  // sumarian sus latencias.
  const [clientes, documentos, uso, claves] = await Promise.all([
    listarClientes(),
    listarDocumentos(id),
    verUso(id),
    listarClaves(id),
  ]);

  const cliente = clientes.find((c) => c.id === id);
  if (!cliente) notFound();

  return (
    <div className="flex-1 bg-zinc-50 px-4 py-10 dark:bg-black">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
        <header>
          <Link href="/panel" className="text-sm text-zinc-500 hover:underline">
            &larr; Clientes
          </Link>
          <h1 className="mt-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
            {cliente.name}
          </h1>
          <p className="text-sm text-zinc-500">{cliente.slug}</p>
        </header>

        {/* --- Comportamiento --- */}
        <Seccion
          titulo="Comportamiento"
          ayuda="Lo que el bot tiene que ser y como responder. Se aplica al instante, sin volver a desplegar."
        >
          <Formulario accion={guardarPrompt} className="flex flex-col gap-3">
            <input type="hidden" name="id" value={id} />
            <textarea
              name="system_prompt"
              rows={7}
              defaultValue={cliente.system_prompt}
              className={claseInput}
            />
            <div>
              <Boton>Guardar comportamiento</Boton>
            </div>
          </Formulario>
        </Seccion>

        {/* --- Documentos --- */}
        <Seccion
          titulo="Base de conocimiento"
          ayuda="De aca saca la informacion para responder. Si actualizas un tarifario, borra el viejo o va a mezclar datos."
        >
          {documentos.length === 0 ? (
            <p className="text-sm text-zinc-500">Sin documentos todav&iacute;a.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {documentos.map((d) => (
                <li
                  key={d.id}
                  className="flex items-center justify-between gap-3 rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-800"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-zinc-900 dark:text-zinc-100">
                      {d.title}
                    </span>
                    <span className="text-xs text-zinc-500">{d.chunks} fragmentos</span>
                  </span>
                  <Formulario accion={borrarDocumento}>
                    <input type="hidden" name="id" value={id} />
                    <input type="hidden" name="doc_id" value={d.id} />
                    <Boton variante="peligro">Borrar</Boton>
                  </Formulario>
                </li>
              ))}
            </ul>
          )}

          <Formulario accion={subirDocumento} className="mt-4 flex flex-col gap-3">
            <input type="hidden" name="id" value={id} />
            <input
              type="file"
              name="file"
              accept=".pdf,.txt,.md"
              required
              className="text-sm text-zinc-600 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-900 file:px-3 file:py-2 file:text-sm file:text-white dark:text-zinc-300 dark:file:bg-zinc-100 dark:file:text-zinc-900"
            />
            <div>
              <Boton variante="suave">Subir documento</Boton>
            </div>
          </Formulario>
        </Seccion>

        {/* --- Consumo --- */}
        <Seccion titulo="Consumo del mes" ayuda={`Periodo ${uso.period}.`}>
          <p className="text-sm text-zinc-900 dark:text-zinc-100">
            {uso.messages} mensajes
            {uso.limit === null ? " (sin tope)" : ` de ${uso.limit}`}
          </p>

          <Formulario accion={guardarLimite} className="mt-3 flex flex-col gap-3">
            <input type="hidden" name="id" value={id} />
            <label className="block text-xs text-zinc-500">
              Tope mensual (vac&iacute;o = sin l&iacute;mite)
              <input
                name="monthly_message_limit"
                inputMode="numeric"
                defaultValue={cliente.monthly_message_limit ?? ""}
                className={`mt-1 ${claseInput}`}
              />
            </label>
            <div>
              <Boton variante="suave">Guardar tope</Boton>
            </div>
          </Formulario>
        </Seccion>

        {/* --- Claves --- */}
        <Seccion
          titulo="Claves de acceso"
          ayuda="La clave 'chat' solo puede conversar: es la que va en el widget de la web del cliente. La clave 'tenant' ademas puede subir documentos."
        >
          {claves.length > 0 && (
            <ul className="mb-4 flex flex-col gap-2">
              {claves.map((k) => (
                <li
                  key={k.id}
                  className="flex items-center justify-between gap-3 rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-800"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm text-zinc-900 dark:text-zinc-100">
                      {k.name}
                    </span>
                    <span className="text-xs text-zinc-500">
                      {k.key_prefix}… · {k.scopes.join(", ")} ·{" "}
                      {k.is_active ? "activa" : "revocada"}
                    </span>
                  </span>
                  {k.is_active && (
                    <Formulario accion={revocarClave}>
                      <input type="hidden" name="id" value={id} />
                      <input type="hidden" name="key_id" value={k.id} />
                      <Boton variante="peligro">Revocar</Boton>
                    </Formulario>
                  )}
                </li>
              ))}
            </ul>
          )}

          <FormularioClave accion={emitirClave} tenantId={id} />
        </Seccion>
      </div>
    </div>
  );
}

function Seccion({
  titulo,
  ayuda,
  children,
}: {
  titulo: string;
  ayuda: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{titulo}</h2>
      <p className="mb-3 text-xs text-zinc-500">{ayuda}</p>
      {children}
    </section>
  );
}
