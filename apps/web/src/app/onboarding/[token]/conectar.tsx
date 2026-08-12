"use client";

import Script from "next/script";
import { useCallback, useEffect, useRef, useState } from "react";

import { conectarWhatsApp } from "../acciones";

// El popup de Meta devuelve el alta en DOS pedazos que llegan por vias
// distintas:
//
//   1. un `message` del popup con el waba_id y el phone_number_id que eligio el
//      cliente, y
//   2. un `code` de autorizacion, por el callback de FB.login.
//
// No hay orden garantizado entre los dos, asi que se guardan a medida que
// llegan y el alta se dispara cuando estan los dos. Con uno solo no alcanza:
// sin el code no hay token, y sin los ids no sabemos que numero conectar.

type DatosSignup = { waba_id: string; phone_number_id: string };

type Estado =
  | { paso: "listo" }
  | { paso: "conectando" }
  | { paso: "ok"; advertencia?: string }
  | { paso: "error"; mensaje: string };

// Solo se aceptan mensajes venidos de Facebook. Sin este filtro, cualquier
// pagina o iframe podria mandarle un `message` a esta ventana con un waba_id
// inventado y hacernos conectar un numero que no es el del cliente.
const ORIGENES_META = ["https://www.facebook.com", "https://web.facebook.com"];

declare global {
  interface Window {
    FB?: {
      init(opciones: Record<string, unknown>): void;
      login(callback: (respuesta: RespuestaFB) => void, opciones: Record<string, unknown>): void;
    };
  }
}

type RespuestaFB = { authResponse?: { code?: string } | null; status?: string };

export function BotonConectar({
  token,
  appId,
  configId,
  apiVersion,
}: {
  token: string;
  appId: string;
  configId: string;
  apiVersion: string;
}) {
  const [estado, setEstado] = useState<Estado>({ paso: "listo" });
  const [sdkListo, setSdkListo] = useState(false);
  const datos = useRef<DatosSignup | null>(null);

  // --- Mensajes del popup ---
  useEffect(() => {
    const alRecibir = (evento: MessageEvent) => {
      if (!ORIGENES_META.includes(evento.origin)) return;

      let cuerpo: {
        type?: string;
        event?: string;
        data?: Record<string, string>;
      };
      try {
        cuerpo = typeof evento.data === "string" ? JSON.parse(evento.data) : evento.data;
      } catch {
        return; // Meta manda otros mensajes por este canal; los que no son JSON no son para nosotros.
      }
      if (cuerpo?.type !== "WA_EMBEDDED_SIGNUP") return;

      if (cuerpo.event === "FINISH" && cuerpo.data?.waba_id && cuerpo.data?.phone_number_id) {
        datos.current = {
          waba_id: cuerpo.data.waba_id,
          phone_number_id: cuerpo.data.phone_number_id,
        };
        return;
      }

      // El cliente cerro el popup a mitad de camino. `current_step` dice donde
      // quedo, y sirve para decirle algo mas util que "fallo".
      if (cuerpo.event === "CANCEL") {
        datos.current = null;
        setEstado({
          paso: "error",
          mensaje: cuerpo.data?.current_step
            ? `Cerraste la ventana antes de terminar (quedaste en: ${cuerpo.data.current_step}). Podes volver a intentarlo.`
            : "Cerraste la ventana antes de terminar. Podes volver a intentarlo.",
        });
      }
    };

    window.addEventListener("message", alRecibir);
    return () => window.removeEventListener("message", alRecibir);
  }, []);

  const finalizar = useCallback(
    async (code: string) => {
      const ids = datos.current;
      if (!ids) {
        setEstado({
          paso: "error",
          mensaje:
            "Facebook no devolvio el numero elegido. Volve a intentarlo y asegurate de llegar hasta el final del asistente.",
        });
        return;
      }

      setEstado({ paso: "conectando" });
      const r = await conectarWhatsApp(token, { code, ...ids });
      // El code es de un solo uso: si el alta fallo, hay que volver a pasar por
      // el popup, no reintentar con el mismo.
      datos.current = null;

      setEstado(
        r.error ? { paso: "error", mensaje: r.error } : { paso: "ok", advertencia: r.advertencia },
      );
    },
    [token],
  );

  const abrirPopup = useCallback(() => {
    if (!window.FB) return;
    setEstado({ paso: "listo" });

    window.FB.login(
      (respuesta) => {
        const code = respuesta?.authResponse?.code;
        if (!code) {
          // Sin code no hay nada que hacer: o cancelo, o no dio los permisos.
          setEstado((previo) =>
            previo.paso === "error"
              ? previo // ya hay un mensaje mas especifico del evento CANCEL
              : {
                  paso: "error",
                  mensaje: "No se completo la autorizacion. Podes volver a intentarlo.",
                },
          );
          return;
        }
        void finalizar(code);
      },
      {
        config_id: configId,
        // Pedimos un `code` en vez de un access token: el token se obtiene en el
        // servidor, que es el unico lado donde vive el App Secret.
        response_type: "code",
        override_default_response_type: true,
        extras: { setup: {}, featureType: "", sessionInfoVersion: "3" },
      },
    );
  }, [configId, finalizar]);

  if (estado.paso === "ok") {
    return (
      <div className="flex flex-col gap-3">
        <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-700 dark:bg-green-950 dark:text-green-300">
          Listo, tu WhatsApp qued&oacute; conectado. Ya pod&eacute;s cerrar esta p&aacute;gina.
        </p>
        {estado.advertencia && (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300">
            {estado.advertencia}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {/* next/script y no un <script> a mano: se encarga de cargarlo una sola
          vez aunque el componente se vuelva a montar. Dos cargas del SDK dejan
          el estado de FB inconsistente y el popup empieza a fallar solo. */}
      <Script
        src="https://connect.facebook.net/en_US/sdk.js"
        crossOrigin="anonymous"
        onReady={() => {
          window.FB?.init({
            appId,
            autoLogAppEvents: true,
            xfbml: true,
            version: apiVersion,
          });
          setSdkListo(true);
        }}
        // Sin esto, con un bloqueador de publicidad el boton se queda en
        // "Cargando…" para siempre y el cliente no sabe que esta esperando.
        onError={() =>
          setEstado({
            paso: "error",
            mensaje:
              "No se pudo cargar el conector de Facebook. Si tenes un bloqueador de publicidad, desactivalo para esta pagina y recarga.",
          })
        }
      />

      <button
        type="button"
        onClick={abrirPopup}
        disabled={!sdkListo || estado.paso === "conectando"}
        className="rounded-md bg-[#1877F2] px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-[#166FE5] disabled:opacity-40"
      >
        {estado.paso === "conectando"
          ? "Conectando…"
          : sdkListo
            ? "Conectar WhatsApp"
            : "Cargando…"}
      </button>

      {estado.paso === "error" && (
        <p
          role="status"
          className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300"
        >
          {estado.mensaje}
        </p>
      )}
    </div>
  );
}
