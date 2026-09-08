import { CamposDeLaFicha } from "@/components/ficha-del-negocio";
import { verFicha } from "@/lib/api";
import { guardarFicha } from "../../acciones";
import { Boton, Formulario } from "../../ui";
import { clienteDelPanel, exigirPanel } from "../../guardia";

export const metadata = { title: "Negocio" };

/**
 * Los datos que el asistente sabe del negocio.
 *
 * ★ ES LA MISMA FICHA QUE EDITA EL DUENIO en /mi-negocio/datos. La agencia la
 * completa en el alta y el duenio la corrige cuando cambia algo, sin que
 * ninguno de los dos tenga que avisarle al otro. Por eso los campos salen de
 * `components/ficha-del-negocio.tsx` y no de aca: si cada lado dibujara los
 * suyos, terminarian viendo fichas distintas del mismo dato.
 *
 * Lo que NO esta aca es el comportamiento del bot: eso vive en Conocimiento y
 * lo toca solo la agencia. La ficha son datos que el asistente cita; el prompt
 * es como se comporta. No son la misma cosa y no se editan en el mismo lugar.
 */
export default async function Negocio({ params }: { params: Promise<{ id: string }> }) {
  await exigirPanel();
  const { id } = await params;

  const [cliente, ficha] = await Promise.all([clienteDelPanel(id), verFicha(id)]);
  if (!cliente) return null; // el layout ya hizo notFound

  return (
    <Formulario accion={guardarFicha} className="flex flex-col gap-6">
      <input type="hidden" name="id" value={id} />

      <CamposDeLaFicha ficha={ficha} />

      {/* Un solo boton para toda la ficha: la API la reemplaza entera, asi que
          guardar por bloque daria la ilusion de tres guardados independientes. */}
      <div className="flex items-center gap-3">
        <Boton>Guardar los datos</Boton>
        <span className="text-xs text-texto-tenue">
          Se aplican al instante, sin volver a desplegar.
        </span>
      </div>
    </Formulario>
  );
}
