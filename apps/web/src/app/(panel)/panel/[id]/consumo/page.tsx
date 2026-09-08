import { Bloque, claseCampo } from "@/components/ui";
import { verUso } from "@/lib/api";
import { guardarLimite } from "../../acciones";
import { Boton, Formulario } from "../../ui";
import { clienteDelPanel, exigirPanel } from "../../guardia";

export const metadata = { title: "Consumo" };

export default async function Consumo({ params }: { params: Promise<{ id: string }> }) {
  await exigirPanel();
  const { id } = await params;

  const [cliente, uso] = await Promise.all([clienteDelPanel(id), verUso(id)]);
  if (!cliente) return null; // el layout ya hizo notFound

  return (
    <Bloque titulo="Consumo del mes" ayuda={`Período ${uso.period}.`}>
      <p className="text-2xl font-semibold tracking-tight text-texto">
        {uso.messages}
        <span className="ml-1.5 text-sm font-normal text-texto-suave">
          {uso.limit === null ? "mensajes (sin tope)" : `de ${uso.limit} mensajes`}
        </span>
      </p>

      <Formulario accion={guardarLimite} className="mt-4 flex flex-col gap-3">
        <input type="hidden" name="id" value={id} />
        <label className="block text-xs text-texto-suave">
          Tope mensual (vac&iacute;o = sin l&iacute;mite)
          <input
            name="monthly_message_limit"
            inputMode="numeric"
            defaultValue={cliente.monthly_message_limit ?? ""}
            className={`mt-1 ${claseCampo}`}
          />
        </label>
        <div>
          <Boton variante="suave">Guardar tope</Boton>
        </div>
      </Formulario>
    </Bloque>
  );
}
