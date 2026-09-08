import { redirect } from "next/navigation";

import { Aviso, Encabezado } from "@/components/ui";
import { ErrorApi, type ResumenCliente, listarResumen } from "@/lib/api";
import { duracion } from "@/lib/duracion";
import { haySesion } from "@/lib/session";
import { Clientes } from "./clientes";
import { AnchoDelPanel, BarraDelPanel } from "./marco";

export const metadata = { title: "Clientes" };

// La pantalla principal: todos los clientes y cual necesita algo.
//
// ★ UNA SOLA LLAMADA PARA TODA LA PANTALLA
// Antes esto pedia la lista de clientes y, aparte, todos los incidentes. Y aun
// asi no alcanzaba para saber si alguien estaba esperando: eso habia que ir a
// buscarlo entrando cliente por cliente. Ahora la API devuelve el resumen ya
// agrupado (ver services/resumen.py), asi que la pantalla es un fetch y un
// render, y el orden -el que espera primero- lo decide la API.

export default async function Panel() {
  if (!(await haySesion())) redirect("/panel/login");

  let clientes: ResumenCliente[];
  try {
    clientes = await listarResumen();
  } catch (e) {
    return (
      <>
        <BarraDelPanel />
        <AnchoDelPanel>
          <Encabezado titulo="Clientes" />
          <Aviso
            error={`No se pudo leer la lista de clientes: ${
              e instanceof ErrorApi ? e.message : "error inesperado"
            }`}
          />
        </AnchoDelPanel>
      </>
    );
  }

  return (
    <>
      <BarraDelPanel />
      <AnchoDelPanel>
        <Encabezado titulo="Clientes" detalle={<Detalle clientes={clientes} />} />
        <Clientes clientes={clientes} />
      </AnchoDelPanel>
    </>
  );
}

/** La linea de abajo del titulo: como viene todo, en una frase.
 *
 *  ★ Dice el ESTADO, no que es la pantalla. "Cada cliente tiene su
 *  comportamiento y sus documentos" era cierto, pero no le sirve a nadie que
 *  ya sabe donde esta parado; lo que hace falta al abrir el panel a la mañana
 *  es saber si hay algo que atender ahora. */
function Detalle({ clientes }: { clientes: ResumenCliente[] }) {
  const negocios = `${clientes.length} ${clientes.length === 1 ? "negocio" : "negocios"}`;
  const esperando = clientes.reduce((total, c) => total + c.esperando, 0);
  const rotos = clientes.filter((c) => c.incidentes > 0).length;

  if (esperando === 0 && rotos === 0) {
    return <>{negocios} · nadie esperando</>;
  }

  // Hace cuanto espera la mas vieja de todas: es lo que dice si esto es urgente
  // o puede esperar al cafe.
  const masVieja = clientes
    .map((c) => c.minutos_de_la_mas_vieja)
    .filter((m): m is number => m !== null)
    .sort((a, b) => b - a)[0];

  return (
    <>
      {negocios}
      {esperando > 0 && (
        <>
          {" · "}
          <span className="font-medium text-alerta">
            {esperando === 1 ? "1 conversación espera" : `${esperando} conversaciones esperan`}
            {masVieja !== undefined && ` desde hace ${duracion(masVieja)}`}
          </span>
        </>
      )}
      {rotos > 0 && (
        <>
          {" · "}
          <span className="font-medium text-error">
            {rotos === 1
              ? "1 cliente con mensajes sin contestar"
              : `${rotos} clientes con mensajes sin contestar`}
          </span>
        </>
      )}
    </>
  );
}
