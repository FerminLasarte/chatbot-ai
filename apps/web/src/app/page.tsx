"use client";

import { claseBoton, claseCampo } from "@/components/ui";

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
    <div className="flex flex-1 flex-col items-center px-4 py-10">
      <div className="flex w-full max-w-2xl flex-col gap-6">
        <header>
          <h1 className="text-2xl font-semibold text-texto">
            Chatbot AI — demo
          </h1>
          <p className="text-sm text-texto-suave">
            Subi un documento y pregunt&aacute;le lo que quieras.
          </p>
        </header>

        {sinClave && (
          <div className="rounded-lg bg-alerta-suave p-4 text-sm text-alerta">
            Falta <code>NEXT_PUBLIC_API_KEY</code> en <code>apps/web/.env.local</code>. Corr&eacute;:
            <pre className="mt-2 overflow-x-auto rounded bg-superficie-2 p-2">
              cd apps/api &amp;&amp; uv run python -m app.cli crear-tenant-demo
            </pre>
            y reinici&aacute; el servidor de Next.js.
          </div>
        )}

        <section className="rounded-xl border border-borde bg-superficie p-5">
          <label className="flex cursor-pointer flex-col items-center gap-2 rounded-md border-2 border-dashed border-borde-fuerte p-6 text-center transition-colors hover:border-acento">
            <span className="text-sm text-texto-suave">
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

        <section className="flex min-h-96 flex-col rounded-xl border border-borde bg-superficie">
          <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
            {mensajes.length === 0 && (
              <p className="m-auto text-sm text-texto-tenue">
                Sin mensajes todav&iacute;a. Escrib&iacute; algo abajo.
              </p>
            )}
            {mensajes.map((m, i) => (
              <div
                key={i}
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  m.rol === "user"
                    ? "self-end bg-acento-suave text-texto"
                    : "self-start bg-superficie-2 text-texto"
                }`}
              >
                {m.texto}
              </div>
            ))}
            {enviando && <p className="self-start text-sm text-texto-tenue">escribiendo...</p>}
          </div>

          <form
            onSubmit={enviarPregunta}
            className="flex gap-2 border-t border-borde p-3"
          >
            <input
              value={pregunta}
              onChange={(e) => setPregunta(e.target.value)}
              placeholder="Escribí tu pregunta..."
              disabled={sinClave}
              className={claseCampo}
            />
            <button
              type="submit"
              disabled={sinClave || enviando || !pregunta.trim()}
              className={claseBoton()}
            >
              Enviar
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
