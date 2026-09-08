import {
  ListaDeConversaciones,
  type FilaDeConversacion,
} from "@/components/conversaciones";
import { EnVivo } from "@/components/en-vivo";
import { Metrica, Metricas } from "@/components/metricas";
import { Bloque, claseCampoAngosto } from "@/components/ui";
import { listarConversaciones, listarIncidentes, verUso, verWhatsApp } from "@/lib/api";
import { cuantasEsperan, type ConversacionEnLista } from "@/lib/conversaciones";
import { duracion } from "@/lib/duracion";
import { exigirPanel } from "../guardia";
import { pausarBot, reanudarBot, responderAlCliente, traerHiloDelCliente } from "../acciones";
import { Boton, Formulario } from "../ui";
import { Incidentes } from "./incidentes";

export const metadata = { title: "Conversaciones" };

export default async function Conversaciones({ params }: { params: Promise<{ id: string }> }) {
  await exigirPanel();
  const { id } = await params;

  const [conversaciones, incidentes, uso, wa] = await Promise.all([
    listarConversaciones(id),
    listarIncidentes(id),
    verUso(id),
    verWhatsApp(id),
  ]);

  const esperando = cuantasEsperan(conversaciones);
  // "Activa" es lo que sigue vivo hoy: mas viejo que eso ya es historial y no
  // dice nada sobre como viene el dia.
  const activas = conversaciones.filter((c) => c.minutos_inactiva < 60 * 24).length;
  // Hace cuanto espera la que espera hace mas. Es lo que dice si esto es
  // urgente: "2 esperando" y "2 esperando hace 4 h" no piden lo mismo.
  const masVieja = conversaciones
    .map((c) => c.minutos_desde_derivacion)
    .filter((m): m is number => m !== null)
    .sort((a, b) => b - a)[0];

  // ★ Las acciones se arman ACA, del lado del servidor, y viajan ya dibujadas.
  // La lista corre en el navegador para poder filtrar en la tecla, y una
  // funcion no cruza esa frontera; el JSX con la Server Action adentro si.
  const filas: FilaDeConversacion[] = conversaciones.map((conversacion) => ({
    conversacion,
    acciones: <AccionesDelHilo conversacion={conversacion} tenantId={id} />,
  }));

  return (
    <>
      <Metricas>
        <Metrica
          etiqueta="Conversaciones hoy"
          valor={activas}
          detalle={`${conversaciones.length} en total`}
        />
        <Metrica
          etiqueta="Esperando una persona"
          valor={esperando}
          detalle={
            esperando > 0
              ? masVieja !== undefined
                ? `la más vieja, hace ${duracion(masVieja)}`
                : "sin atender"
              : "nadie en espera"
          }
          tono={esperando > 0 ? "alerta" : "neutro"}
        />
        <Metrica
          etiqueta="Mensajes del mes"
          valor={uso.messages.toLocaleString("es-AR")}
          detalle={
            uso.limit === null ? "sin tope" : `de ${uso.limit.toLocaleString("es-AR")}`
          }
        />
        <Metrica
          etiqueta="WhatsApp"
          valor={wa.configurado ? "Conectado" : "Sin conectar"}
          detalle={wa.configurado ? "el bot puede responder" : "el bot no puede responder"}
          tono={wa.configurado ? "ok" : "alerta"}
        />
      </Metricas>

      <Incidentes incidentes={incidentes} />

      <Bloque
        titulo="Conversaciones"
        ayuda="Entrá a una para leer el hilo, contestar vos mismo, o callar al bot mientras la atendés."
        acciones={<EnVivo />}
        alBorde
      >
        <ListaDeConversaciones
          filas={filas}
          // "A mano" y no "Vos": del lado de la agencia, quien contesto desde el
          // celular es el comercio, no quien esta mirando el panel.
          etiquetaPersona="A mano"
          traer={traerHiloDelCliente.bind(null, id)}
          responder={responderAlCliente.bind(null, id)}
          vacio={{
            titulo: "Todavía no le escribió nadie",
            detalle:
              "Cuando alguien le mande un WhatsApp al negocio, la conversación aparece acá sola.",
          }}
        />
      </Bloque>
    </>
  );
}

/** Callar o reactivar al bot en una conversacion, al pie de su panel. */
function AccionesDelHilo({
  conversacion,
  tenantId,
}: {
  conversacion: ConversacionEnLista;
  tenantId: string;
}) {
  if (conversacion.en_modo_manual) {
    return (
      <Formulario accion={reanudarBot}>
        <input type="hidden" name="id" value={tenantId} />
        <input type="hidden" name="conversacion_id" value={conversacion.id} />
        <Boton variante="suave">Que vuelva a responder el bot</Boton>
      </Formulario>
    );
  }

  return (
    <Formulario accion={pausarBot}>
      <input type="hidden" name="id" value={tenantId} />
      <input type="hidden" name="conversacion_id" value={conversacion.id} />
      <div className="flex flex-wrap items-center gap-2">
        <select name="horas" defaultValue="8" className={claseCampoAngosto}>
          <option value="1">1 hora</option>
          <option value="4">4 horas</option>
          <option value="8">8 horas</option>
          <option value="24">24 horas</option>
        </select>
        <Boton variante="suave">Pausar el bot</Boton>
      </div>
    </Formulario>
  );
}
