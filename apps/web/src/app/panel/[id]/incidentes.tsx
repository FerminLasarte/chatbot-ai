import { Bloque } from "@/components/ui";
import type { Incidente } from "@/lib/api";

/**
 * Mensajes que entraron y el bot no llego a contestar.
 *
 * ★ Solo aparece si hay alguno, y va primero: es lo unico de esta pantalla que
 * significa que un cliente esta siendo mal atendido AHORA. Cuando no hay nada
 * que reportar, no ocupa lugar.
 */
export function Incidentes({ incidentes }: { incidentes: Incidente[] }) {
  if (incidentes.length === 0) return null;

  return (
    <Bloque
      titulo="Mensajes sin contestar"
      ayuda="Entraron pero el bot no llegó a responderlos. 'Fallado' es que algo explotó; 'colgado' es que se perdió en un reinicio del servidor. Al usuario final no le llegó nada."
    >
      <ul className="flex flex-col gap-3">
        {incidentes.map((i) => (
          <li key={i.id} className="rounded-lg bg-error-suave p-3 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-medium text-error">
                {i.status === "failed" ? "Fallado" : "Colgado"}
                {i.channel === "whatsapp" ? " — WhatsApp" : ` — ${i.channel}`}
              </span>
              <span className="text-xs text-error">
                hace {i.minutos < 60 ? `${i.minutos} min` : `${Math.round(i.minutos / 60)} h`}
                {i.attempts > 1 && ` · ${i.attempts} intentos`}
              </span>
            </div>
            {i.error && (
              <p className="mt-2 overflow-x-auto font-mono text-xs text-error">{i.error}</p>
            )}
          </li>
        ))}
      </ul>
    </Bloque>
  );
}
