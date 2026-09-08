import { ListaDeConversaciones, type FilaDeConversacion } from "@/components/conversaciones";
import { EnVivo } from "@/components/en-vivo";
import { Bloque, claseCampoAngosto } from "@/components/ui";
import { cuantasEsperan, type ConversacionEnLista } from "@/lib/conversaciones";
import { duracion } from "@/lib/duracion";
import { AccesoRevocado, listarMisConversaciones, verMiNegocio } from "@/lib/portal";
import { claveDelPortal } from "@/lib/sesion-portal";
import { pausarBot, reanudarBot, responderYo, traerMiHilo } from "./acciones";
import { EncabezadoDelPortal, Marco, SinAcceso } from "./marco";
import { Boton, FormularioPortal } from "./ui";

// Esta pagina la abre el duenio de la PyME, no la agencia. Junto con
// /onboarding es de las pocas que viven fuera de /panel y no piden la
// contrasena de la agencia: la credencial es la clave que quedo en la cookie al
// abrir el link (ver lib/sesion-portal.ts).
//
// ★ ESTA ES LA CARA DEL PRODUCTO. El panel lo ve la agencia; esto lo ve quien
// paga. Por eso vive en la piel `papel` -clara, con aire, con tipografia de
// titulos propia- y no en la del panel, que es una cabina de mando mas densa,
// pensada para mirar ocho horas (ver globals.css).
export const metadata = {
  title: "Mi negocio",
  // Una pagina a la que se entra con un link no tiene por que estar en Google.
  robots: { index: false, follow: false },
};

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
        detalle="Puede que te hayan mandado uno nuevo, o que lo hayan dado de baja. Pedile el link actualizado a quien te lo pasó."
      />
    );
  }
  if (link === "error") {
    return (
      <SinAcceso
        titulo="No pudimos abrir tu página"
        detalle="Fue un problema nuestro, no del link. Probá de nuevo en unos minutos con el mismo link."
      />
    );
  }

  if (!clave) {
    return (
      <SinAcceso
        titulo="Entrá con tu link"
        detalle="Para ver tus conversaciones abrí el link que te pasaron por mail o WhatsApp. Guardalo en favoritos: sirve todas las veces que quieras."
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
          detalle="El link con el que entraste ya no tiene permiso. Pedile uno nuevo a quien te lo pasó."
        />
      );
    }
    return (
      <SinAcceso
        titulo="No pudimos cargar tus conversaciones"
        detalle="Fue un problema nuestro. Probá de nuevo en unos minutos."
      />
    );
  }

  const esperando = cuantasEsperan(conversaciones);
  const masVieja = conversaciones
    .map((c) => c.minutos_desde_derivacion)
    .filter((m): m is number => m !== null)
    .sort((a, b) => b - a)[0];

  // Las acciones se arman en el servidor y viajan ya dibujadas: la lista corre
  // en el navegador para poder filtrar en la tecla. Ver components/conversaciones.tsx.
  const filas: FilaDeConversacion[] = conversaciones.map((conversacion) => ({
    conversacion,
    acciones: <AccionesDelHilo conversacion={conversacion} />,
  }));

  return (
    <Marco>
      <EncabezadoDelPortal
        nombre={negocio.nombre}
        esperando={esperando}
        estado={
          /* ★ La linea de abajo dice como viene, no que es la pagina. Quien la
             abre ya sabe que es su negocio; lo que necesita saber es si hay
             alguien esperandolo ahora mismo. */
          esperando > 0 ? (
            <span className="font-medium text-alerta">
              {esperando === 1
                ? "1 persona está esperando que la atiendas"
                : `${esperando} personas están esperando que las atiendas`}
              {masVieja !== undefined && ` · la que más, hace ${duracion(masVieja)}`}
            </span>
          ) : (
            "Todo atendido. Estas son las conversaciones de tu asistente."
          )
        }
      />

      <Bloque
        titulo="Conversaciones"
        ayuda="Podés contestar vos mismo desde acá. Cuando lo hacés, el asistente se calla solo en esa conversación para no pisarte."
        acciones={<EnVivo />}
        alBorde
      >
        <ListaDeConversaciones
          filas={filas}
          etiquetaPersona="Vos"
          traer={traerMiHilo}
          responder={responderYo}
          vacio={{
            titulo: "Todavía no te escribió nadie",
            detalle:
              "Cuando alguien le escriba a tu WhatsApp, la conversación va a aparecer acá sola.",
          }}
        />
      </Bloque>

      <p className="text-xs text-texto-tenue">
        Esta p&aacute;gina es solo tuya: muestra &uacute;nicamente las conversaciones de tu
        negocio. Si perd&eacute;s el link o cre&eacute;s que lo vio alguien m&aacute;s,
        avisale a quien te lo pas&oacute; para que te den uno nuevo.
      </p>
    </Marco>
  );
}

/** Lo que se puede hacer con una conversacion, al pie de su panel.
 *
 * ★ Solo va el id. La credencial sale de la cookie dentro de la accion, nunca
 * de un campo del formulario: una Server Action es un endpoint HTTP y cualquiera
 * puede mandarle el FormData que quiera. Ver la nota de acciones.ts.
 */
function AccionesDelHilo({ conversacion }: { conversacion: ConversacionEnLista }) {
  if (conversacion.en_modo_manual) {
    return (
      <FormularioPortal accion={reanudarBot}>
        <input type="hidden" name="conversacion_id" value={conversacion.id} />
        <Boton variante="suave">Que vuelva a responder el asistente</Boton>
      </FormularioPortal>
    );
  }

  return (
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
  );
}
