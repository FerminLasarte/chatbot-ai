import {
  AccesoRevocado,
  listarMisConversaciones,
  verMiNegocio,
  type ConversacionDelPortal,
} from "@/lib/portal";
import { claveDelPortal } from "@/lib/sesion-portal";
import { Bloque, Chip, Vacio, claseCampoAngosto } from "@/components/ui";
import { duracion } from "@/lib/duracion";
import { pausarBot, reanudarBot, traerMiHilo } from "./acciones";
import { VerConversacion } from "@/components/hilo";
import { Boton, FormularioPortal } from "./ui";

// Esta pagina la abre el duenio de la PyME, no la agencia. Junto con
// /onboarding es de las pocas que viven fuera de /panel y no piden la
// contrasena de la agencia: la credencial es la clave que quedo en la cookie al
// abrir el link (ver lib/sesion-portal.ts).
export const metadata = {
  title: "Mi negocio",
  // Una pagina a la que se entra con un link no tiene por que estar en Google.
  robots: { index: false, follow: false },
};

function Marco({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 px-4 py-10 sm:py-14">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">{children}</div>
    </div>
  );
}

/** Pantalla de "no puedo dejarte pasar", redactada para alguien no tecnico. */
function SinAcceso({ titulo, detalle }: { titulo: string; detalle: string }) {
  return (
    <Marco>
      <section className="rounded-xl border border-borde bg-superficie p-6">
        <h1 className="text-lg font-semibold text-texto">{titulo}</h1>
        <p className="mt-2 text-sm text-texto-suave">{detalle}</p>
      </section>
    </Marco>
  );
}

export default async function MiNegocio({
  searchParams,
}: {
  searchParams: Promise<{ link?: string }>;
}) {
  const { link } = await searchParams;
  const clave = await claveDelPortal();

  // El route handler de /mi-negocio/[token] redirige aca con esta marca cuando
  // el link no sirvio. Se atiende antes que la cookie: si alguien abre un link
  // vencido teniendo una sesion vieja, lo que quiere saber es que ESE link fallo.
  if (link === "invalido") {
    return (
      <SinAcceso
        titulo="Este link ya no sirve"
        detalle="Puede que te hayan mandado uno nuevo, o que lo hayan dado de baja. Pedile el link actualizado a quien te lo paso."
      />
    );
  }
  if (link === "error") {
    return (
      <SinAcceso
        titulo="No pudimos abrir tu pagina"
        detalle="Fue un problema nuestro, no del link. Proba de nuevo en unos minutos con el mismo link."
      />
    );
  }

  if (!clave) {
    return (
      <SinAcceso
        titulo="Entra con tu link"
        detalle="Para ver tus conversaciones abri el link que te pasaron por mail o WhatsApp. Guardalo en favoritos: sirve todas las veces que quieras."
      />
    );
  }

  let negocio;
  let conversaciones;
  try {
    // En paralelo: son dos consultas independientes y en serie sumarian sus
    // latencias.
    [negocio, conversaciones] = await Promise.all([
      verMiNegocio(clave),
      listarMisConversaciones(clave),
    ]);
  } catch (e) {
    if (e instanceof AccesoRevocado) {
      return (
        <SinAcceso
          titulo="Tu acceso fue dado de baja"
          detalle="El link con el que entraste ya no tiene permiso. Pedile uno nuevo a quien te lo paso."
        />
      );
    }
    return (
      <SinAcceso
        titulo="No pudimos cargar tus conversaciones"
        detalle="Fue un problema nuestro. Proba de nuevo en unos minutos."
      />
    );
  }

  // Las que esperan una persona, arriba de todo; el resto conserva el orden que
  // manda la API (la ultima actividad primero).
  const ordenadas = [...conversaciones].sort(
    (a, b) => Number(b.derivada) - Number(a.derivada),
  );
  const esperando = conversaciones.filter((c) => c.derivada).length;

  return (
    <Marco>
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-texto">{negocio.nombre}</h1>
        <p className="mt-1 text-sm text-texto-suave">
          Las conversaciones que tuvo tu asistente por WhatsApp.
        </p>
      </header>

      {/* ★ Las que pidieron una persona van primero, sin importar cuando fue el
          ultimo mensaje. Es lo unico de esta pantalla donde alguien esta
          esperando: enterrado entre veinte conversaciones ordenadas por fecha,
          el aviso no sirve de nada. */}
      <Bloque
        titulo="Conversaciones"
        ayuda="Si querés atender a alguien vos mismo, pausá el asistente desde la conversación así no te pisa la respuesta. Vuelve solo cuando pasa el tiempo que elijas."
        acciones={
          esperando > 0 ? (
            <Chip tono="alerta">
              {esperando === 1 ? "1 esperando" : `${esperando} esperando`}
            </Chip>
          ) : null
        }
      >
        {conversaciones.length === 0 ? (
          <Vacio>Todavía no te escribió nadie. Cuando lo hagan, van a aparecer acá.</Vacio>
        ) : (
          <ul className="-my-1 flex flex-col divide-y divide-borde">
            {ordenadas.map((c) => (
              <Hilo key={c.id} conversacion={c} />
            ))}
          </ul>
        )}
      </Bloque>

      <p className="text-xs text-texto-tenue">
        Esta p&aacute;gina es solo tuya: muestra &uacute;nicamente las conversaciones de tu
        negocio. Si perd&eacute;s el link o cre&eacute;s que lo vio alguien m&aacute;s,
        avisale a quien te lo pas&oacute; para que te den uno nuevo.
      </p>
    </Marco>
  );
}

/** Una fila de la lista: quien escribio, en que estado quedo y como entrar.
 *
 * ★ Las acciones (pausar, reactivar) NO viven aca sino al pie del panel de la
 * conversacion. En una lista de veinte hilos, veinte desplegables de horas y
 * veinte botones son ruido que tapa lo unico que importa a simple vista: quien
 * esta esperando. La accion vive donde uno ya esta mirando de que se trata.
 */
function Hilo({ conversacion }: { conversacion: ConversacionDelPortal }) {
  const esWhatsApp = conversacion.channel === "whatsapp";
  const quien = esWhatsApp ? `+${conversacion.external_id}` : conversacion.external_id;

  return (
    <li className="flex items-start justify-between gap-3 py-3">
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium text-texto">{quien}</span>
          {conversacion.derivada && (
            <Chip tono="alerta">
              Pidieron una persona
              {conversacion.minutos_desde_derivacion !== null &&
                ` · hace ${duracion(conversacion.minutos_desde_derivacion)}`}
            </Chip>
          )}
          {conversacion.minutos_restantes !== null && (
            <Chip>Lo atendés vos · vuelve en {duracion(conversacion.minutos_restantes)}</Chip>
          )}
        </span>

        {conversacion.ultimo_mensaje && (
          <span className="mt-1 block truncate text-sm text-texto-suave">
            {conversacion.ultimo_mensaje}
          </span>
        )}

        <span className="mt-1 block text-xs text-texto-tenue">
          {conversacion.mensajes} {conversacion.mensajes === 1 ? "mensaje" : "mensajes"}
          {" · hace "}
          {duracion(conversacion.minutos_inactiva)}
        </span>
      </span>

      <VerConversacion
        conversacionId={conversacion.id}
        titulo={quien}
        subtitulo={`${conversacion.mensajes} ${
          conversacion.mensajes === 1 ? "mensaje" : "mensajes"
        } · hace ${duracion(conversacion.minutos_inactiva)}`}
        etiquetaPersona="Vos"
        traer={traerMiHilo}
      >
        {/* ★ Solo va el id de la conversacion. La credencial sale de la cookie
            dentro de la accion, nunca de un campo del formulario. Ver la nota
            de acciones.ts. */}
        {conversacion.en_modo_manual ? (
          <FormularioPortal accion={reanudarBot}>
            <input type="hidden" name="conversacion_id" value={conversacion.id} />
            <Boton>Que vuelva a responder el asistente</Boton>
          </FormularioPortal>
        ) : (
          <FormularioPortal accion={pausarBot}>
            <input type="hidden" name="conversacion_id" value={conversacion.id} />
            <div className="flex flex-wrap items-center gap-2">
              <select name="horas" defaultValue="8" className={claseCampoAngosto}>
                <option value="1">1 hora</option>
                <option value="4">4 horas</option>
                <option value="8">8 horas</option>
                <option value="24">24 horas</option>
              </select>
              <Boton variante="suave">Pausar el asistente</Boton>
            </div>
          </FormularioPortal>
        )}
      </VerConversacion>
    </li>
  );
}
