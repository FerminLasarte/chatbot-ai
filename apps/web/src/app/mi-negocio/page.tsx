import {
  AccesoRevocado,
  listarMisConversaciones,
  verMiNegocio,
  type ConversacionDelPortal,
} from "@/lib/portal";
import { claveDelPortal } from "@/lib/sesion-portal";
import { claseCampoAngosto } from "@/lib/estilos";
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
    <div className="flex-1 bg-zinc-50 px-4 py-10 dark:bg-black">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">{children}</div>
    </div>
  );
}

/** Pantalla de "no puedo dejarte pasar", redactada para alguien no tecnico. */
function SinAcceso({ titulo, detalle }: { titulo: string; detalle: string }) {
  return (
    <Marco>
      <section className="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">{titulo}</h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{detalle}</p>
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

  return (
    <Marco>
      <header>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">{negocio.nombre}</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Las conversaciones que tuvo tu asistente por WhatsApp.
        </p>
      </header>

      <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Conversaciones</h2>
        <p className="mb-3 text-xs text-zinc-500">
          Si quer&eacute;s atender a alguien vos mismo, pausa el asistente en esa
          conversaci&oacute;n as&iacute; no te pisa la respuesta mientras escrib&iacute;s. Se
          reactiva solo cuando pasa el tiempo que elijas.
        </p>

        {conversaciones.length === 0 ? (
          <p className="text-sm text-zinc-500">
            Todav&iacute;a no te escribi&oacute; nadie. Cuando lo hagan, van a aparecer
            ac&aacute;.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {conversaciones.map((c) => (
              <Hilo key={c.id} conversacion={c} />
            ))}
          </ul>
        )}
      </section>

      <p className="text-xs text-zinc-500">
        Esta p&aacute;gina es solo tuya: muestra &uacute;nicamente las conversaciones de tu
        negocio. Si perd&eacute;s el link o cre&eacute;s que lo vio alguien m&aacute;s,
        avisale a quien te lo pas&oacute; para que te den uno nuevo.
      </p>
    </Marco>
  );
}

/** Una conversacion con su estado y el interruptor del asistente. */
function Hilo({ conversacion }: { conversacion: ConversacionDelPortal }) {
  const esWhatsApp = conversacion.channel === "whatsapp";
  return (
    <li className="rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-800">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <span className="min-w-0">
          <span className="block truncate text-sm text-zinc-900 dark:text-zinc-100">
            {esWhatsApp ? `+${conversacion.external_id}` : conversacion.external_id}
          </span>

          {/* Va arriba y a la izquierda, antes que el adelanto del mensaje: es
              lo unico de esta fila que pide una accion, y quien barre la lista
              lo hace leyendo la columna izquierda de arriba abajo. */}
          {conversacion.derivada && (
            <span className="my-1 inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              <span className="size-1.5 rounded-full bg-amber-500" />
              Pidieron una persona
              {conversacion.minutos_desde_derivacion !== null &&
                ` · hace ${duracion(conversacion.minutos_desde_derivacion)}`}
            </span>
          )}

          {conversacion.ultimo_mensaje && (
            <span className="block truncate text-xs text-zinc-500">
              {conversacion.ultimo_mensaje}
            </span>
          )}
          <span className="text-xs text-zinc-500">
            {conversacion.mensajes} {conversacion.mensajes === 1 ? "mensaje" : "mensajes"}{" "}
            &middot; hace {duracion(conversacion.minutos_inactiva)}
          </span>
        </span>

        <span className="flex shrink-0 flex-col items-end gap-1">
          {conversacion.minutos_restantes !== null && (
            <span className="text-xs text-amber-700 dark:text-amber-400">
              Lo atend&eacute;s vos &mdash; el asistente vuelve en{" "}
              {duracion(conversacion.minutos_restantes)}
            </span>
          )}
          {/* "Vos" y no "A mano": del lado del duenio del negocio, la persona
              que contesto desde el celular es el mismo. */}
          <VerConversacion
            conversacionId={conversacion.id}
            titulo={esWhatsApp ? `+${conversacion.external_id}` : conversacion.external_id}
            subtitulo={`${conversacion.mensajes} ${
              conversacion.mensajes === 1 ? "mensaje" : "mensajes"
            } · hace ${duracion(conversacion.minutos_inactiva)}`}
            etiquetaPersona="Vos"
            traer={traerMiHilo}
          />
        </span>
      </div>

      {/* ★ Solo va el id de la conversacion. La credencial sale de la cookie
          dentro de la accion, nunca de un campo del formulario. Ver la nota de
          acciones.ts. */}
      {conversacion.en_modo_manual ? (
        <FormularioPortal accion={reanudarBot} className="mt-2">
          <input type="hidden" name="conversacion_id" value={conversacion.id} />
          <Boton>Que vuelva a responder el asistente</Boton>
        </FormularioPortal>
      ) : (
        <FormularioPortal accion={pausarBot} className="mt-2">
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
    </li>
  );
}
