import { Bloque, Chip } from "@/components/ui";
import { listarClaves } from "@/lib/api";
import { emitirClave, generarLinkPortal, revocarClave } from "../../acciones";
import { Boton, Formulario, FormularioClave, FormularioLink } from "../../ui";
import { exigirPanel } from "../../guardia";

export const metadata = { title: "Accesos" };

export default async function Accesos({ params }: { params: Promise<{ id: string }> }) {
  await exigirPanel();
  const { id } = await params;
  const claves = await listarClaves(id);

  // El link del portal ES una clave con scope client_portal, asi que el estado
  // se lee de la misma lista de abajo: no hace falta un endpoint aparte.
  const tienePortal = claves.some((k) => k.is_active && k.scopes.includes("client_portal"));

  return (
    <>
      <Bloque
        titulo="Acceso del cliente"
        ayuda="Un link para que el dueño del negocio vea sus conversaciones y pause el bot él mismo. No ve nada más: ni documentos, ni credenciales, ni consumo, ni otros clientes."
        acciones={tienePortal ? <Chip tono="ok">Con acceso</Chip> : null}
      >
        <p className="mb-3 text-sm text-texto-suave">
          {tienePortal
            ? "Si lo perdió o se le filtró, generá otro: el anterior deja de funcionar en el acto."
            : "Todavía no tiene acceso propio."}
        </p>

        <FormularioLinkDelPortal id={id} tienePortal={tienePortal} />
      </Bloque>

      <Bloque
        titulo="Claves de acceso"
        ayuda="La clave 'chat' solo puede conversar: es la que va en el widget de la web del cliente. La clave 'tenant' además puede subir documentos."
      >
        {claves.length > 0 && (
          <ul className="-mt-1 mb-4 flex flex-col divide-y divide-borde">
            {claves.map((k) => (
              <li key={k.id} className="flex items-center justify-between gap-3 py-2.5">
                <span className="min-w-0">
                  <span className="block truncate text-sm text-texto">{k.name}</span>
                  <span className="text-xs text-texto-tenue">
                    {k.key_prefix}… · {k.scopes.join(", ")} · {k.is_active ? "activa" : "revocada"}
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
      </Bloque>
    </>
  );
}

/** Aparte para que el bloque de arriba se lea de un vistazo. */
function FormularioLinkDelPortal({ id, tienePortal }: { id: string; tienePortal: boolean }) {
  return (
    <FormularioLink
      accion={generarLinkPortal}
      tenantId={id}
      etiqueta="Generar link de acceso"
      etiquetaRepetir="Generar otro link"
      variante={tienePortal ? "suave" : "normal"}
    />
  );
}
