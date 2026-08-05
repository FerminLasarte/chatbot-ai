"use client";

import { FormEvent, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

// El backend responde JSON, pero un 500 sin manejar de FastAPI viene en texto
// plano: hacer res.json() a ciegas rompe ahi y el error real queda tapado por
// un "no se pudo conectar" que miente sobre lo que paso.
async function leerError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return data.detail ?? `error ${res.status}`;
  } catch {
    return `error ${res.status} del servidor`;
  }
}

type Mensaje = { rol: "user" | "assistant"; texto: string };

type EstadoDocumento =
  | { tipo: "vacio" }
  | { tipo: "subiendo"; nombre: string }
  | { tipo: "listo"; nombre: string; chunks: number }
  | { tipo: "error"; mensaje: string };

export default function Home() {
  const [documento, setDocumento] = useState<EstadoDocumento>({ tipo: "vacio" });
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [pregunta, setPregunta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const conversationId = useRef<string | null>(null);

  const sinClave = !API_KEY;

  async function subirArchivo(file: File) {
    setDocumento({ tipo: "subiendo", nombre: file.name });
    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch(`${API_URL}/api/v1/knowledge/documents`, {
        method: "POST",
        headers: { Authorization: `Bearer ${API_KEY}` },
        body: form,
      });
      if (!res.ok) {
        setDocumento({ tipo: "error", mensaje: await leerError(res) });
        return;
      }
      const data = await res.json();
      setDocumento({ tipo: "listo", nombre: data.title, chunks: data.chunks });
      setMensajes([]);
      conversationId.current = null;
    } catch {
      setDocumento({ tipo: "error", mensaje: "no se pudo conectar con el servidor" });
    }
  }

  async function enviarPregunta(e: FormEvent) {
    e.preventDefault();
    const texto = pregunta.trim();
    if (!texto || enviando) return;

    setMensajes((m) => [...m, { rol: "user", texto }]);
    setPregunta("");
    setEnviando(true);

    try {
      const res = await fetch(`${API_URL}/api/v1/chat`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: texto,
          conversation_id: conversationId.current,
        }),
      });
      if (!res.ok) {
        const error = await leerError(res);
        setMensajes((m) => [...m, { rol: "assistant", texto: error }]);
        return;
      }
      const data = await res.json();
      conversationId.current = data.conversation_id;
      setMensajes((m) => [...m, { rol: "assistant", texto: data.reply }]);
    } catch {
      setMensajes((m) => [
        ...m,
        { rol: "assistant", texto: "No se pudo conectar con el servidor." },
      ]);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col items-center bg-zinc-50 px-4 py-10 dark:bg-black">
      <div className="flex w-full max-w-2xl flex-col gap-6">
        <header>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
            Chatbot AI — demo
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Subi un documento y pregunt&aacute;le lo que quieras.
          </p>
        </header>

        {sinClave && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
            Falta <code>NEXT_PUBLIC_API_KEY</code> en <code>apps/web/.env.local</code>. Corr&eacute;:
            <pre className="mt-2 overflow-x-auto rounded bg-black/10 p-2 dark:bg-white/10">
              cd apps/api &amp;&amp; uv run python -m app.cli crear-tenant-demo
            </pre>
            y reinici&aacute; el servidor de Next.js.
          </div>
        )}

        <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <label className="flex cursor-pointer flex-col items-center gap-2 rounded-md border-2 border-dashed border-zinc-300 p-6 text-center hover:border-zinc-400 dark:border-zinc-700 dark:hover:border-zinc-600">
            <span className="text-sm text-zinc-600 dark:text-zinc-300">
              {documento.tipo === "vacio" && "Hacé click para elegir un PDF, .txt o .md"}
              {documento.tipo === "subiendo" && `Subiendo ${documento.nombre}...`}
              {documento.tipo === "listo" &&
                `${documento.nombre} — ${documento.chunks} fragmentos indexados`}
              {documento.tipo === "error" && documento.mensaje}
            </span>
            <input
              type="file"
              accept=".pdf,.txt,.md"
              className="hidden"
              disabled={sinClave || documento.tipo === "subiendo"}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void subirArchivo(file);
              }}
            />
          </label>
        </section>

        <section className="flex min-h-96 flex-col rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
            {mensajes.length === 0 && (
              <p className="m-auto text-sm text-zinc-400">
                Sin mensajes todav&iacute;a. Escrib&iacute; algo abajo.
              </p>
            )}
            {mensajes.map((m, i) => (
              <div
                key={i}
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  m.rol === "user"
                    ? "self-end bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "self-start bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                }`}
              >
                {m.texto}
              </div>
            ))}
            {enviando && <p className="self-start text-sm text-zinc-400">escribiendo...</p>}
          </div>

          <form
            onSubmit={enviarPregunta}
            className="flex gap-2 border-t border-zinc-200 p-3 dark:border-zinc-800"
          >
            <input
              value={pregunta}
              onChange={(e) => setPregunta(e.target.value)}
              placeholder="Escribí tu pregunta..."
              disabled={sinClave}
              className="flex-1 rounded-md border border-zinc-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700"
            />
            <button
              type="submit"
              disabled={sinClave || enviando || !pregunta.trim()}
              className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
            >
              Enviar
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
