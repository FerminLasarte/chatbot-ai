"use client";

import { useState } from "react";

import { Repetible, FilaRepetible } from "@/components/repetible";
import { Bloque, CampoDeHora, Etiqueta, claseCampo, claseCampoAngosto } from "@/components/ui";
import {
  DIAS,
  MAX_EXTRAS,
  MAX_TRAMOS_POR_DIA,
  hhmm,
  type BloqueExtra,
  type Ficha,
  type TramoHorario,
} from "@/lib/ficha";

// Los campos de la ficha del negocio, compartidos por las dos puertas.
//
// ★ QUE COMPARTE Y QUE NO
// Comparte los CAMPOS: cuales son, en que orden, como se llaman y como se
// dibujan. Lo que no comparte es el formulario ni la accion: cada lado lo
// envuelve en el suyo -`Formulario` en el panel, `FormularioPortal` en el
// portal- con su credencial y su tipo de estado. Es la misma frontera que ya
// tienen la lista de conversaciones y el hilo.
//
// Si el panel y el portal tuvieran cada uno su version de estos campos, el dia
// que se agregue "zona horaria" habria que acordarse de agregarla dos veces, y
// el dueño y la agencia terminarian viendo fichas distintas de lo mismo.
//
// ★ LOS VALORES VIVEN EN EL DOM, NO EN REACT
// El estado de aca es SOLO que filas existen. Lo que hay escrito adentro lo
// guarda el navegador, como en cualquier formulario. Por eso las filas llevan
// una `key` estable y no el indice: con el indice, quitar la primera fila le
// correria el valor a todas las de abajo.

/** Una fila de horario mientras se la edita. El `id` solo sirve de `key`. */
type FilaHorario = { id: string; desde?: string; hasta?: string };
type FilaExtra = { id: string; titulo?: string; texto?: string };

let proximoId = 0;
const nuevoId = () => `f${proximoId++}`;

function porDia(horarios: readonly TramoHorario[]): FilaHorario[][] {
  const semana: FilaHorario[][] = DIAS.map(() => []);
  for (const t of horarios) {
    if (t.dia >= 0 && t.dia < DIAS.length) {
      semana[t.dia].push({ id: nuevoId(), desde: hhmm(t.desde), hasta: hhmm(t.hasta) });
    }
  }
  return semana;
}

export function CamposDeLaFicha({ ficha }: { ficha: Ficha }) {
  return (
    <div className="flex flex-col gap-6">
      <Bloque
        titulo="Datos del negocio"
        ayuda="Con esto contesta el asistente cuando le preguntan. Lo que dejes vacío, simplemente no lo sabe."
      >
        <div className="flex flex-col gap-4">
          <CampoLargo
            name="direccion"
            etiqueta="Dirección"
            ayuda="Dónde queda y cómo llegar."
            placeholder="Av. Siempreviva 742, a media cuadra de la plaza"
            defaultValue={ficha.direccion}
            filas={2}
          />
          <CampoLargo
            name="envios"
            etiqueta="Envíos y retiros"
            ayuda="A dónde llegan, cuánto tardan, cuánto cuestan."
            placeholder="Hacemos envíos en el día dentro de la ciudad. Retiro por el local sin costo."
            defaultValue={ficha.envios}
          />
          <CampoLargo
            name="medios_de_pago"
            etiqueta="Medios de pago"
            placeholder="Efectivo, transferencia y todas las tarjetas."
            defaultValue={ficha.medios_de_pago}
            filas={2}
          />
          <CampoLargo
            name="web_y_redes"
            etiqueta="Web y redes"
            placeholder="@minegocio en Instagram · minegocio.com.ar"
            defaultValue={ficha.web_y_redes}
            filas={2}
          />
          {/* ★ El campo menos evidente y el que mas problemas evita: es lo que
              frena al asistente de prometer algo que el negocio no hace. */}
          <CampoLargo
            name="no_hacemos"
            etiqueta="Lo que NO hacemos"
            ayuda="Para que el asistente no prometa algo que después no podés cumplir."
            placeholder="No tomamos reservas por WhatsApp. No hacemos envíos al interior."
            defaultValue={ficha.no_hacemos}
          />
        </div>
      </Bloque>

      <Bloque
        titulo="Horarios"
        ayuda="Los días que dejes sin horario, el asistente los dice como cerrados."
      >
        <Horarios inicial={ficha.horarios} />
      </Bloque>

      <Bloque
        titulo="Algo más que deba saber"
        ayuda="Cualquier cosa que no entre en los campos de arriba: estacionamiento, promociones, si es apto celíacos."
      >
        <Extras inicial={ficha.extras} />
      </Bloque>
    </div>
  );
}

/** Un campo de texto de varias lineas, con su etiqueta arriba. */
function CampoLargo({
  name,
  etiqueta,
  ayuda,
  placeholder,
  defaultValue,
  filas = 3,
}: {
  name: string;
  etiqueta: string;
  ayuda?: string;
  placeholder: string;
  defaultValue: string | null;
  filas?: number;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <Etiqueta ayuda={ayuda}>{etiqueta}</Etiqueta>
      <textarea
        name={name}
        rows={filas}
        defaultValue={defaultValue ?? ""}
        placeholder={placeholder}
        className={claseCampo}
      />
    </label>
  );
}

/**
 * La semana entera, un dia por fila.
 *
 * ★ SE MUESTRAN LOS SIETE DIAS, INCLUSO LOS CERRADOS. La alternativa -una lista
 * plana de tramos con un desplegable de dia en cada uno- ocupa menos, pero deja
 * la pregunta importante sin responder: mirando la pantalla no se sabe si el
 * domingo esta cerrado o si nadie lo cargo todavia. Y para el que pregunta un
 * domingo, esas dos cosas son muy distintas.
 */
function Horarios({ inicial }: { inicial: readonly TramoHorario[] }) {
  const [semana, setSemana] = useState<FilaHorario[][]>(() => porDia(inicial));

  const cambiar = (dia: number, filas: FilaHorario[]) =>
    setSemana((antes) => antes.map((f, i) => (i === dia ? filas : f)));

  return (
    <div className="flex flex-col divide-y divide-borde">
      {DIAS.map((nombre, dia) => (
        <div
          key={nombre}
          className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:gap-4"
        >
          <span className="pt-1.5 text-sm font-medium text-texto capitalize sm:w-28 sm:shrink-0">
            {nombre}
          </span>

          <div className="min-w-0 flex-1">
            <Repetible
              cuantas={semana[dia].length}
              maximo={MAX_TRAMOS_POR_DIA}
              alAgregar={() => cambiar(dia, [...semana[dia], { id: nuevoId() }])}
              etiquetaAgregar={semana[dia].length === 0 ? "Abre este día" : "Otro horario"}
              vacio="Cerrado"
            >
              {semana[dia].map((fila) => (
                <FilaRepetible
                  key={fila.id}
                  alQuitar={() =>
                    cambiar(
                      dia,
                      semana[dia].filter((f) => f.id !== fila.id),
                    )
                  }
                  etiquetaQuitar={`Quitar este horario del ${nombre}`}
                >
                  {/* El dia no lo elige nadie: lo dice la fila en la que esta.
                      Viaja igual porque el FormData es plano. */}
                  <input type="hidden" name="tramo_dia" value={dia} />
                  <CampoDeHora
                    name="tramo_desde"
                    defaultValue={fila.desde}
                    etiqueta={`Hora en que abre el ${nombre}`}
                    required
                  />
                  <span className="text-sm text-texto-suave">a</span>
                  <CampoDeHora
                    name="tramo_hasta"
                    defaultValue={fila.hasta}
                    etiqueta={`Hora en que cierra el ${nombre}`}
                    required
                  />
                </FilaRepetible>
              ))}
            </Repetible>
          </div>
        </div>
      ))}

      {/* ★ Se dice una sola vez, abajo de todo, y no en cada fila: es la duda
          que aparece al cargar el primer negocio gastronomico. */}
      <p className="pt-3 text-xs text-texto-tenue">
        Si cerr&aacute;s despu&eacute;s de medianoche, carg&aacute; por ejemplo de 20:00 a
        00:30.
      </p>
    </div>
  );
}

/** Los bloques libres: la valvula de escape de la ficha. */
function Extras({ inicial }: { inicial: readonly BloqueExtra[] }) {
  const [filas, setFilas] = useState<FilaExtra[]>(() =>
    inicial.map((b) => ({ id: nuevoId(), titulo: b.titulo, texto: b.texto })),
  );

  return (
    <Repetible
      cuantas={filas.length}
      maximo={MAX_EXTRAS}
      alAgregar={() => setFilas([...filas, { id: nuevoId() }])}
      etiquetaAgregar={filas.length === 0 ? "Agregar algo" : "Agregar otro"}
      vacio="Nada más por ahora. Si hay algo que te preguntan seguido, agregalo acá."
    >
      {filas.map((fila) => (
        <FilaRepetible
          key={fila.id}
          forma="bloque"
          alQuitar={() => setFilas(filas.filter((f) => f.id !== fila.id))}
          etiquetaQuitar={fila.titulo ? `Quitar "${fila.titulo}"` : "Quitar esto"}
        >
          <div className="flex flex-col gap-2">
            <input
              name="extra_titulo"
              defaultValue={fila.titulo}
              placeholder="Estacionamiento"
              maxLength={60}
              className={`${claseCampoAngosto} w-full sm:w-64`}
              aria-label="De qué se trata"
            />
            <textarea
              name="extra_texto"
              rows={2}
              defaultValue={fila.texto}
              placeholder="Hay cochera en la esquina, con descuento mostrando el ticket."
              maxLength={500}
              className={claseCampo}
              aria-label="Qué tiene que saber el asistente"
            />
          </div>
        </FilaRepetible>
      ))}
    </Repetible>
  );
}
