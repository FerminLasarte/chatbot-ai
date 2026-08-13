import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import {
  listarClaves,
  listarClientes,
  listarConversaciones,
  listarDocumentos,
  listarIncidentes,
  verUso,
  verWhatsApp,
} from "@/lib/api";
import type { Conversacion } from "@/lib/api";
import { haySesion } from "@/lib/session";
import {
  borrarDocumento,
  borrarTokenWhatsApp,
  emitirClave,
  generarLinkOnboarding,
  guardarLimite,
  guardarPrompt,
  guardarWhatsApp,
  pausarBot,
  reanudarBot,
  revocarClave,
  subirDocumento,
} from "../acciones";
import { Boton, Formulario, FormularioClave, FormularioLinkOnboarding } from "../ui";
import { claseInput } from "@/lib/estilos";

export const metadata = { title: "Panel — cliente" };

export default async function Cliente({ params }: { params: Promise<{ id: string }> }) {
  if (!(await haySesion())) redirect("/panel/login");

  const { id } = await params;

  // Se piden en paralelo: son consultas independientes y en serie sumarian sus
  // latencias.
  const [clientes, documentos, uso, claves, wa, conversaciones, incidentes] = await Promise.all([
    listarClientes(),
    listarDocumentos(id),
    verUso(id),
    listarClaves(id),
    verWhatsApp(id),
    listarConversaciones(id),
    listarIncidentes(id),
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

        {/* --- Mensajes sin contestar ---
            Va primero y solo aparece si hay algo: es lo unico de esta pagina
            que significa que el cliente esta siendo mal atendido AHORA. */}
        {incidentes.length > 0 && (
          <Seccion
            titulo="Mensajes sin contestar"
            ayuda="Entraron pero el bot no llego a responderlos. 'fallado' es que algo exploto; 'colgado' es que se perdio en un reinicio del servidor. Al usuario final no le llego nada."
          >
            <ul className="flex flex-col gap-3">
              {incidentes.map((i) => (
                <li
                  key={i.id}
                  className="rounded-md border border-red-200 bg-red-50 p-3 text-sm dark:border-red-900 dark:bg-red-950"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-medium text-red-800 dark:text-red-300">
                      {i.status === "failed" ? "Fallado" : "Colgado"}
                      {i.channel === "whatsapp" ? " — WhatsApp" : ` — ${i.channel}`}
                    </span>
                    <span className="text-xs text-red-700 dark:text-red-400">
                      hace {i.minutos < 60 ? `${i.minutos} min` : `${Math.round(i.minutos / 60)} h`}
                      {i.attempts > 1 && ` · ${i.attempts} intentos`}
                    </span>
                  </div>
                  {i.error && (
                    <p className="mt-2 overflow-x-auto font-mono text-xs text-red-900 dark:text-red-300">
                      {i.error}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </Seccion>
        )}

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

        {/* --- WhatsApp --- */}
        <Seccion
          titulo="WhatsApp"
          ayuda="Conecta el numero del cliente. Sin las dos cosas cargadas, el bot no puede responder por WhatsApp."
        >
          <p className="mb-3 text-sm">
            {wa.configurado ? (
              <span className="text-green-700 dark:text-green-400">
                Conectado — el bot responde por WhatsApp.
              </span>
            ) : (
              <span className="text-amber-700 dark:text-amber-400">
                {wa.phone_number_id && !wa.tiene_token
                  ? "Falta el access token."
                  : wa.tiene_token && !wa.phone_number_id
                    ? "Falta el numero (phone number ID)."
                    : "Sin configurar."}
              </span>
            )}
          </p>

          <FormularioLinkOnboarding
            accion={generarLinkOnboarding}
            tenantId={id}
            yaConectado={wa.configurado}
          />

          {/* La carga a mano sigue existiendo, pero plegada: es la salida de
              emergencia, no el camino normal. */}
          <details className="mt-5">
            <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
              Cargar las credenciales a mano
            </summary>
            <p className="mt-2 mb-3 text-xs text-zinc-500">
              Solo hace falta si el cliente no puede usar el link (por ejemplo, si su
              n&uacute;mero ya estaba dado de alta en otra App de Meta).
            </p>

            <Formulario accion={guardarWhatsApp} className="flex flex-col gap-3">
              <input type="hidden" name="id" value={id} />
              <label className="block text-xs text-zinc-500">
                Phone number ID (lo da Meta, no es el n&uacute;mero telef&oacute;nico)
                <input
                  name="phone_number_id"
                  defaultValue={wa.phone_number_id ?? ""}
                  placeholder="123456789012345"
                  className={`mt-1 ${claseInput}`}
                />
              </label>
              <label className="block text-xs text-zinc-500">
                Access token{" "}
                {wa.tiene_token && "(ya hay uno guardado; dejalo vacio para no cambiarlo)"}
                <input
                  name="access_token"
                  type="password"
                  autoComplete="off"
                  placeholder={wa.tiene_token ? "••••••••" : "EAAG..."}
                  className={`mt-1 ${claseInput}`}
                />
              </label>
              <div className="flex gap-2">
                <Boton>Guardar WhatsApp</Boton>
              </div>
            </Formulario>

            {wa.tiene_token && (
              <Formulario accion={borrarTokenWhatsApp} className="mt-3">
                <input type="hidden" name="id" value={id} />
                <Boton variante="peligro">Borrar token</Boton>
              </Formulario>
            )}
          </details>
        </Seccion>

        {/* --- Conversaciones --- */}
        <Seccion
          titulo="Conversaciones"
          ayuda="Si queres atender a alguien vos mismo desde Meta Business Suite, pausa el bot en esa conversacion asi no te pisa la respuesta. La pausa se apaga sola."
        >
          {conversaciones.length === 0 ? (
            <p className="text-sm text-zinc-500">Todav&iacute;a no hay conversaciones.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {conversaciones.map((c) => (
                <Hilo key={c.id} conversacion={c} tenantId={id} />
              ))}
            </ul>
          )}
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

/** Una conversacion con su estado y el interruptor del modo manual. */
function Hilo({ conversacion, tenantId }: { conversacion: Conversacion; tenantId: string }) {
  const esWhatsApp = conversacion.channel === "whatsapp";
  return (
    <li className="rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-800">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <span className="min-w-0">
          <span className="block truncate text-sm text-zinc-900 dark:text-zinc-100">
            {esWhatsApp ? `+${conversacion.external_id}` : conversacion.external_id}
          </span>
          {conversacion.ultimo_mensaje && (
            <span className="block truncate text-xs text-zinc-500">
              {conversacion.ultimo_mensaje}
            </span>
          )}
          <span className="text-xs text-zinc-500">
            {esWhatsApp ? "WhatsApp" : conversacion.channel} &middot; {conversacion.mensajes}{" "}
            mensajes &middot; hace {duracion(conversacion.minutos_inactiva)}
          </span>
        </span>

        {conversacion.minutos_restantes !== null && (
          <span className="text-xs text-amber-700 dark:text-amber-400">
            Lo atend&eacute;s vos &mdash; el bot vuelve en{" "}
            {duracion(conversacion.minutos_restantes)}
          </span>
        )}
      </div>

      {conversacion.en_modo_manual ? (
        <Formulario accion={reanudarBot} className="mt-2">
          <input type="hidden" name="id" value={tenantId} />
          <input type="hidden" name="conversacion_id" value={conversacion.id} />
          <Boton>Que responda el bot</Boton>
        </Formulario>
      ) : (
        <Formulario accion={pausarBot} className="mt-2 flex flex-wrap items-center gap-2">
          <input type="hidden" name="id" value={tenantId} />
          <input type="hidden" name="conversacion_id" value={conversacion.id} />
          <select name="horas" defaultValue="8" className={`${claseInput} w-auto`}>
            <option value="1">1 hora</option>
            <option value="4">4 horas</option>
            <option value="8">8 horas</option>
            <option value="24">24 horas</option>
          </select>
          <Boton variante="suave">Pausar el bot</Boton>
        </Formulario>
      )}
    </li>
  );
}

/**
 * Minutos -> texto corto ("40 min", "2 h 15 min", "3 d").
 *
 * Solo formatea: los minutos vienen calculados de la API. Ver el comentario de
 * `Conversacion` en lib/api.ts para por que el reloj esta de aquel lado.
 */
function duracion(minutos: number): string {
  if (minutos < 60) return `${minutos} min`;

  const horas = Math.floor(minutos / 60);
  if (horas < 24) {
    const resto = minutos % 60;
    return resto === 0 ? `${horas} h` : `${horas} h ${resto} min`;
  }
  return `${Math.floor(horas / 24)} d`;
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
