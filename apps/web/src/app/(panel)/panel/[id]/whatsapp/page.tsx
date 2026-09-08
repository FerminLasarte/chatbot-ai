import { Bloque, Chip, claseCampo } from "@/components/ui";
import { verWhatsApp } from "@/lib/api";
import { borrarTokenWhatsApp, generarLinkOnboarding, guardarWhatsApp } from "../../acciones";
import { Boton, Formulario, FormularioLink } from "../../ui";
import { exigirPanel } from "../../guardia";

export const metadata = { title: "WhatsApp" };

export default async function WhatsApp({ params }: { params: Promise<{ id: string }> }) {
  await exigirPanel();
  const { id } = await params;
  const wa = await verWhatsApp(id);

  return (
    <>
      <Bloque
        titulo="WhatsApp"
        ayuda="El camino normal es mandarle el link al cliente: lo conecta él solo, sin tocar Business Manager."
        acciones={
          wa.configurado ? (
            <Chip tono="ok">Conectado</Chip>
          ) : (
            <Chip tono="alerta">{faltaQue(wa)}</Chip>
          )
        }
      >
        <FormularioLink
          accion={generarLinkOnboarding}
          tenantId={id}
          etiqueta="Generar link para el cliente"
          etiquetaRepetir="Generar otro link"
          variante={wa.configurado ? "suave" : "normal"}
        />

        {/* Los dos ids que identifican al cliente del lado de Meta. Estan a la
            vista, y no plegados con la carga a mano, porque son lo primero que
            hay que buscar cuando Meta rechaza algo. */}
        {(wa.phone_number_id || wa.waba_id) && (
          <dl className="mt-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
            <dt className="text-texto-suave">Phone number ID</dt>
            <dd className="font-mono break-all text-texto">{wa.phone_number_id ?? "—"}</dd>
            <dt className="text-texto-suave">WABA ID</dt>
            <dd className="font-mono break-all text-texto">
              {wa.waba_id ?? (
                <span className="font-sans text-texto-tenue">
                  sin guardar (alta anterior o carga a mano)
                </span>
              )}
            </dd>
          </dl>
        )}
      </Bloque>

      {/* ★ La carga a mano vive en su propio bloque y al final: es la salida de
          emergencia, no el camino. Mezclada con lo de arriba invitaba a pegar
          tokens cuando alcanzaba con mandar un link. */}
      <Bloque
        titulo="Credenciales a mano"
        ayuda="Solo hace falta si el cliente no puede usar el link, por ejemplo si su número ya estaba dado de alta en otra App de Meta."
      >
        <Formulario accion={guardarWhatsApp} className="flex flex-col gap-3">
          <input type="hidden" name="id" value={id} />
          <label className="block text-xs text-texto-suave">
            Phone number ID (lo da Meta, no es el n&uacute;mero telef&oacute;nico)
            <input
              name="phone_number_id"
              defaultValue={wa.phone_number_id ?? ""}
              placeholder="123456789012345"
              className={`mt-1 ${claseCampo}`}
            />
          </label>
          <label className="block text-xs text-texto-suave">
            Access token{" "}
            {wa.tiene_token && "(ya hay uno guardado; dejalo vacío para no cambiarlo)"}
            <input
              name="access_token"
              type="password"
              autoComplete="off"
              placeholder={wa.tiene_token ? "••••••••" : "EAAG..."}
              className={`mt-1 ${claseCampo}`}
            />
          </label>
          <div className="flex gap-2">
            <Boton variante="suave">Guardar WhatsApp</Boton>
          </div>
        </Formulario>

        {wa.tiene_token && (
          <Formulario accion={borrarTokenWhatsApp} className="mt-3">
            <input type="hidden" name="id" value={id} />
            <Boton variante="peligro">Borrar token</Boton>
          </Formulario>
        )}
      </Bloque>
    </>
  );
}

/** Que falta para que el bot pueda responder por WhatsApp. */
function faltaQue(wa: { phone_number_id: string | null; tiene_token: boolean }): string {
  if (wa.phone_number_id && !wa.tiene_token) return "Falta el token";
  if (wa.tiene_token && !wa.phone_number_id) return "Falta el número";
  return "Sin configurar";
}
