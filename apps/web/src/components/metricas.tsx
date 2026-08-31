import { Tarjeta } from "@/components/ui";

// Los numeros que contestan "como viene esto" sin entrar a ninguna seccion.
//
// ★ NO SON ADORNO
// Una pantalla se siente vacia cuando no dice nada, no cuando le sobra espacio.
// Todo lo que hay aca sale de datos que la API ya devolvia y que estaban
// escondidos adentro de alguna seccion: habia que entrar a Consumo para saber
// cuantos mensajes iban en el mes, y a WhatsApp para saber si el bot podia
// contestar. Ninguna metrica nueva pide un endpoint nuevo.

type Tono = "neutro" | "alerta" | "ok" | "error";

const COLOR_DEL_VALOR: Record<Tono, string> = {
  neutro: "text-texto",
  alerta: "text-alerta",
  ok: "text-ok",
  error: "text-error",
};

export function Metrica({
  etiqueta,
  valor,
  detalle,
  tono = "neutro",
}: {
  /** Que se esta midiendo, en dos o tres palabras. */
  etiqueta: string;
  /** El numero, o una palabra corta cuando no hay numero ("Conectado"). */
  valor: string | number;
  /** La letra chica: contra que se compara, o desde cuando. */
  detalle?: string;
  tono?: Tono;
}) {
  return (
    <Tarjeta className="px-4 py-3.5">
      <p className="text-xs text-texto-suave">{etiqueta}</p>
      <p className={`mt-1 text-2xl font-semibold tracking-tight ${COLOR_DEL_VALOR[tono]}`}>
        {valor}
      </p>
      {detalle && <p className="mt-0.5 text-xs text-texto-tenue">{detalle}</p>}
    </Tarjeta>
  );
}

/** La fila de metricas. En pantalla angosta se apilan de a dos. */
export function Metricas({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{children}</div>;
}
