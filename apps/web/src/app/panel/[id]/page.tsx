import { Bloque, Chip } from "@/components/ui";
import { ListaDeConversaciones, cuantasEsperan, type ConversacionEnLista } from "@/components/conversaciones";
import { listarConversaciones, listarIncidentes, verUso, verWhatsApp } from "@/lib/api";
import { Metrica, Metricas } from "@/components/metricas";
import { claseCampoAngosto } from "@/components/ui";
import { exigirPanel } from "../guardia";
import { pausarBot, reanudarBot, traerHiloDelCliente } from "../acciones";
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
          detalle={esperando > 0 ? "sin atender" : "nadie en espera"}
          tono={esperando > 0 ? "alerta" : "neutro"}
        />
        <Metrica
          etiqueta="Mensajes del mes"
          valor={uso.messages}
          detalle={uso.limit === null ? "sin tope" : `de ${uso.limit}`}
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
        ayuda="Las últimas del cliente. Entrá a una para leer el hilo completo o para callar al bot mientras alguien atiende a mano."
        acciones={
          esperando > 0 ? (
            <Chip tono="alerta">
              {esperando === 1 ? "1 esperando" : `${esperando} esperando`}
            </Chip>
          ) : null
        }
      >
        <ListaDeConversaciones
          conversaciones={conversaciones}
          // "A mano" y no "Vos": del lado de la agencia, quien contesto desde el
          // celular es el comercio, no quien esta mirando el panel.
          etiquetaPersona="A mano"
          traer={traerHiloDelCliente.bind(null, id)}
          vacio="Todavía no le escribió nadie."
          acciones={(c) => <AccionesDelHilo conversacion={c} tenantId={id} />}
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
        <Boton>Que vuelva a responder el bot</Boton>
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
