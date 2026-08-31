import { Bloque, Vacio, claseCampo } from "@/components/ui";
import { listarDocumentos } from "@/lib/api";
import { borrarDocumento, guardarPrompt, subirDocumento } from "../../acciones";
import { Boton, Formulario } from "../../ui";
import { clienteDelPanel, exigirPanel } from "../../guardia";

export const metadata = { title: "Conocimiento" };

/** Lo que el bot es y lo que sabe: las dos cosas que definen que contesta. */
export default async function Conocimiento({ params }: { params: Promise<{ id: string }> }) {
  await exigirPanel();
  const { id } = await params;

  const [cliente, documentos] = await Promise.all([clienteDelPanel(id), listarDocumentos(id)]);
  if (!cliente) return null; // el layout ya hizo notFound

  return (
    <>
      <Bloque
        titulo="Comportamiento"
        ayuda="Lo que el bot tiene que ser y cómo responder. Se aplica al instante, sin volver a desplegar."
      >
        <Formulario accion={guardarPrompt} className="flex flex-col gap-3">
          <input type="hidden" name="id" value={id} />
          <textarea
            name="system_prompt"
            rows={8}
            defaultValue={cliente.system_prompt}
            className={claseCampo}
          />
          <div>
            <Boton>Guardar comportamiento</Boton>
          </div>
        </Formulario>
      </Bloque>

      <Bloque
        titulo="Base de conocimiento"
        ayuda="De acá saca la información para responder. Si actualizás un tarifario, borrá el viejo o va a mezclar datos."
      >
        {documentos.length === 0 ? (
          <Vacio>Sin documentos todavía.</Vacio>
        ) : (
          <ul className="-mt-1 flex flex-col divide-y divide-borde">
            {documentos.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-3 py-2.5">
                <span className="min-w-0">
                  <span className="block truncate text-sm text-texto">{d.title}</span>
                  <span className="text-xs text-texto-tenue">{d.chunks} fragmentos</span>
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
            className="text-sm text-texto-suave file:mr-3 file:rounded-lg file:border-0 file:bg-superficie-2 file:px-3 file:py-2 file:text-sm file:text-texto"
          />
          <div>
            <Boton variante="suave">Subir documento</Boton>
          </div>
        </Formulario>
      </Bloque>
    </>
  );
}
