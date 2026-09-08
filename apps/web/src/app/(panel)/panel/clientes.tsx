"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { IconoBuscar, IconoMas } from "@/components/iconos";
import { PanelLateral } from "@/components/panel-lateral";
import { Chip, Vacio, claseBoton, claseCampo } from "@/components/ui";
import { duracion } from "@/lib/duracion";
import type { ResumenCliente } from "@/lib/api";
import { nuevoCliente } from "./acciones";
import { Boton, Formulario } from "./ui";

// La lista de clientes.
//
// ★ POR QUE ES UN COMPONENTE DE CLIENTE SI LOS DATOS VIENEN DEL SERVIDOR
// Buscar y filtrar tienen que ser instantaneos: con seis clientes cualquier
// cosa alcanza, pero el momento en que esto se usa de verdad es cuando hay
// treinta y hay que encontrar uno. Ir al servidor por cada tecla seria un
// viaje por letra para filtrar una lista que ya esta entera en la pagina.
// El servidor trae los datos una vez; el filtrado es local.

type Filtro = "todos" | "esperando" | "problemas";

const FILTROS: { valor: Filtro; etiqueta: string }[] = [
  { valor: "todos", etiqueta: "Todos" },
  { valor: "esperando", etiqueta: "Esperando" },
  { valor: "problemas", etiqueta: "Con problemas" },
];

/** Un cliente "con problemas" es uno donde el bot no esta atendiendo bien:
 *  mensajes que no se contestaron, o directamente WhatsApp sin conectar. */
function tieneProblemas(c: ResumenCliente): boolean {
  return c.incidentes > 0 || !c.whatsapp_configurado || !c.is_active;
}

export function Clientes({ clientes }: { clientes: ResumenCliente[] }) {
  const [busqueda, setBusqueda] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [creando, setCreando] = useState(false);

  const visibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return clientes.filter((c) => {
      // Se busca por nombre Y por slug: el slug es lo que uno recuerda cuando
      // viene de mirar un log o una URL.
      if (q && !`${c.name} ${c.slug}`.toLowerCase().includes(q)) return false;
      if (filtro === "esperando") return c.esperando > 0;
      if (filtro === "problemas") return tieneProblemas(c);
      return true;
    });
  }, [clientes, busqueda, filtro]);

  const cuantos = (f: Filtro) =>
    f === "esperando"
      ? clientes.filter((c) => c.esperando > 0).length
      : f === "problemas"
        ? clientes.filter(tieneProblemas).length
        : clientes.length;

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative">
            <span className="sr-only">Buscar cliente</span>
            <IconoBuscar className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-texto-tenue" />
            <input
              type="search"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar cliente"
              className={`${claseCampo} w-56 py-1.5 pl-8 text-xs`}
            />
          </label>

          <div className="flex gap-1">
            {FILTROS.map(({ valor, etiqueta }) => {
              const activo = filtro === valor;
              const n = cuantos(valor);
              return (
                <button
                  key={valor}
                  type="button"
                  onClick={() => setFiltro(valor)}
                  aria-pressed={activo}
                  className={`rounded-control px-2.5 py-1.5 text-xs transition-colors ${
                    activo
                      ? "bg-superficie-2 font-medium text-texto"
                      : "text-texto-suave hover:bg-superficie-2 hover:text-texto"
                  }`}
                >
                  {etiqueta}
                  <span className="tabular ml-1.5 text-texto-tenue">{n}</span>
                </button>
              );
            })}
          </div>
        </div>

        <button type="button" onClick={() => setCreando(true)} className={claseBoton("principal")}>
          <IconoMas className="size-3.5" />
          Nuevo cliente
        </button>
      </div>

      <div className="overflow-hidden rounded-panel border border-borde bg-superficie shadow-panel">
        {visibles.length === 0 ? (
          <VacioSegunElCaso hayClientes={clientes.length > 0} alCrear={() => setCreando(true)} />
        ) : (
          <ul>
            {visibles.map((c) => (
              <FilaDeCliente key={c.id} cliente={c} />
            ))}
          </ul>
        )}
      </div>

      {/* ★ El alta va en un panel al costado y no colgada abajo de la lista.
          Un formulario permanente al pie hace que la pantalla se lea como un
          formulario con una lista arriba, cuando lo que se hace todos los dias
          es mirar la lista y lo que se hace una vez por cliente es crearlo. */}
      <PanelLateral
        abierto={creando}
        titulo="Nuevo cliente"
        subtitulo="Después vas a poder conectarle el WhatsApp y cargarle documentos."
        alCerrar={() => setCreando(false)}
      >
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <FormularioDeAlta />
        </div>
      </PanelLateral>
    </>
  );
}

function VacioSegunElCaso({
  hayClientes,
  alCrear,
}: {
  hayClientes: boolean;
  alCrear: () => void;
}) {
  // Que no haya resultados de una busqueda y que no haya clientes son dos
  // situaciones distintas: una se arregla borrando la busqueda y la otra
  // creando un cliente. Decirle "sin datos" a las dos no ayuda a ninguna.
  if (hayClientes) {
    return <Vacio titulo="Ningún cliente coincide">Probá con otro nombre, o cambiá el filtro.</Vacio>;
  }
  return (
    <Vacio
      titulo="Todavía no hay ningún cliente"
      accion={
        <button type="button" onClick={alCrear} className={claseBoton("principal")}>
          Crear el primero
        </button>
      }
    >
      Cuando crees uno vas a poder conectarle su WhatsApp y ver acá todas sus conversaciones.
    </Vacio>
  );
}

/** Una fila: quien es, que necesita, y como viene.
 *
 *  ★ La franja de color a la izquierda es el unico adorno de la fila, y
 *  significa algo: naranja es "alguien esta esperando", rojo es "el bot no
 *  esta contestando". Se ve desde el otro lado de la pantalla, que es
 *  exactamente lo que se necesita al abrir el panel a la mañana. */
function FilaDeCliente({ cliente: c }: { cliente: ResumenCliente }) {
  const franja =
    c.esperando > 0
      ? "shadow-[inset_3px_0_0_var(--alerta)]"
      : c.incidentes > 0
        ? "shadow-[inset_3px_0_0_var(--error)]"
        : "";

  return (
    <li className="border-t border-borde first:border-t-0">
      <Link
        href={`/panel/${c.id}`}
        className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-4 py-fila transition-colors hover:bg-superficie-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)_auto_auto] ${franja}`}
      >
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium text-texto">{c.name}</span>
          <span className="tabular block truncate font-mono text-[11px] text-texto-tenue">
            {c.slug}
          </span>
        </span>

        <span className="col-span-2 flex flex-wrap items-center gap-1.5 lg:col-span-1">
          {c.esperando > 0 && (
            <Chip tono="alerta">
              {c.esperando === 1 ? "1 esperando" : `${c.esperando} esperando`}
              {c.minutos_de_la_mas_vieja !== null &&
                ` · hace ${duracion(c.minutos_de_la_mas_vieja)}`}
            </Chip>
          )}
          {c.incidentes > 0 && (
            <Chip tono="error">
              {c.incidentes === 1 ? "1 sin contestar" : `${c.incidentes} sin contestar`}
            </Chip>
          )}
          {!c.whatsapp_configurado && <Chip tono="alerta">WhatsApp sin conectar</Chip>}
          {!c.is_active && <Chip tono="neutro">Inactivo</Chip>}
          {!c.tiene_portal && c.whatsapp_configurado && (
            <Chip tono="neutro">Sin acceso del dueño</Chip>
          )}
        </span>

        <span className="tabular hidden text-right text-xs whitespace-nowrap text-texto-suave lg:block">
          {c.mensajes_del_mes.toLocaleString("es-AR")}
          <span className="text-texto-tenue">
            {c.limite_mensual === null
              ? " msj este mes"
              : ` / ${c.limite_mensual.toLocaleString("es-AR")}`}
          </span>
        </span>

        <span className="tabular text-right text-[11px] whitespace-nowrap text-texto-tenue lg:w-24">
          {c.minutos_ultima_actividad === null
            ? "sin actividad"
            : `hace ${duracion(c.minutos_ultima_actividad)}`}
        </span>
      </Link>
    </li>
  );
}

/** El alta, adentro del panel lateral. */
function FormularioDeAlta() {
  return (
    <Formulario accion={nuevoCliente} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-texto">Nombre del negocio</span>
        <input
          name="name"
          required
          placeholder="Cabañas Altos de la Sierra"
          className={claseCampo}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-texto">Identificador</span>
        <span className="text-xs text-texto-suave">
          Minúsculas y sin espacios. Es como aparece en los links y en los logs.
        </span>
        <input
          name="slug"
          required
          pattern="[a-z0-9-]+"
          placeholder="cabanas-altos"
          className={`tabular font-mono ${claseCampo}`}
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-texto">Cómo se tiene que comportar</span>
        <span className="text-xs text-texto-suave">
          El tono y los límites del asistente. Los horarios y precios no van acá: van en la
          ficha y en los documentos.
        </span>
        <textarea
          name="system_prompt"
          rows={6}
          placeholder="Sos el asistente de Cabañas Altos de la Sierra. Tono cordial. No inventes precios ni disponibilidad; si no sabés algo, ofrecé pasar el contacto de recepción."
          className={claseCampo}
        />
      </label>

      <div>
        <Boton>Crear cliente</Boton>
      </div>
    </Formulario>
  );
}
