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

// ★ Lo que devuelve el popup se guarda en sessionStorage, no solo en memoria.
//
// No es una precaucion teorica: es el modo de falla del alta desde el celular,
// que es como la abre casi todo el mundo. Para terminar el asistente hay que
// salir a la app de WhatsApp Business, y al volver iOS ya descarto la pestania.
// Con el estado solo en memoria eso borra lo que Meta habia devuelto, y el
// cliente se encuentra la pagina como al principio, sin un solo error a la
// vista, cuando del lado de Meta el alta quedo hecha.
const CLAVE_DATOS = (token: string) => `alta-whatsapp:${token}`;

// El asistente de Meta caduca a las 24 h. Datos mas viejos que eso ya no sirven
// para completar nada y lo unico que harian es prometer un atajo que no existe.
const VIGENCIA_MS = 24 * 60 * 60 * 1000;

function leerGuardado(token: string): DatosSignup | null {
  try {
    const crudo = sessionStorage.getItem(CLAVE_DATOS(token));
    if (!crudo) return null;
    const { waba_id, phone_number_id, ts } = JSON.parse(crudo);
    if (!waba_id || !phone_number_id || Date.now() - ts > VIGENCIA_MS) return null;
    return { waba_id, phone_number_id };
  } catch {
    // Safari en navegacion privada tira al tocar sessionStorage. Que no se
    // pueda recordar no es razon para romper el alta: se sigue sin memoria.
    return null;
  }
}

function guardarDatos(token: string, datos: DatosSignup): void {
  try {
    sessionStorage.setItem(CLAVE_DATOS(token), JSON.stringify({ ...datos, ts: Date.now() }));
  } catch {
    /* ver leerGuardado */
  }
}

function olvidarDatos(token: string): void {
  try {
    sessionStorage.removeItem(CLAVE_DATOS(token));
  } catch {
    /* ver leerGuardado */
  }
}

// Los dos caminos de alta. NO son la misma pantalla de Meta con un detalle
// distinto: el `featureType` decide cual de los dos asistentes abre el popup, y
// elegir mal deja al cliente sin salida.
//
//   "existente" -> coexistence. El numero que ya vive en la app WhatsApp
//                  Business del celular queda tambien en la Cloud API. Pide
//                  escanear un QR, asi que el celular tiene que estar en la
//                  mano.
//   "nuevo"     -> el alta estandar, la que ya andaba. Da de alta un numero que
//                  no esta en ninguna app.
//
// ★ Con `featureType: ""` (lo que habia antes para los dos casos) Meta abre
// siempre el asistente estandar. A alguien que venia a conectar SU numero le
// ofrece un numero virtual nuevo, que es exactamente lo contrario de lo que
// vino a hacer.
const FEATURE_TYPE = {
  existente: "whatsapp_business_app_onboarding",
  nuevo: "",
} as const;

type Camino = keyof typeof FEATURE_TYPE;

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
  children,
}: {
  token: string;
  appId: string;
  configId: string;
  apiVersion: string;
  /** El aviso de terminos y privacidad. Lo pone la pagina, se dibuja aca para
   *  que quede entre la eleccion del numero y el boton. */
  children?: React.ReactNode;
}) {
  const [estado, setEstado] = useState<Estado>({ paso: "listo" });
  const [sdkListo, setSdkListo] = useState(false);
  // Sin default a proposito: los dos caminos son irreversibles para el cliente y
  // ninguno es el "normal". Que elija.
  const [camino, setCamino] = useState<Camino | null>(null);
  const datos = useRef<DatosSignup | null>(null);
  // El alta quedo a medias en un intento anterior y se puede retomar.
  const [retomable, setRetomable] = useState(false);
  // El navegador se comio la ventana emergente (ver `espera`).
  const [sinVentana, setSinVentana] = useState(false);
  const espera = useRef<number | null>(null);

  // --- Rescate de un intento anterior ---
  // Si la pestania se recargo despues de que Meta devolviera los datos, aca es
  // donde se recuperan.
  //
  // La lectura va en un timeout y no en el cuerpo del efecto por dos razones
  // que apuntan al mismo lado: sessionStorage no existe cuando la pagina se
  // renderiza en el servidor, asi que leerlo antes de la hidratacion daria un
  // HTML distinto del que mando el servidor; y setState sincrono dentro de un
  // efecto encadena renders (el linter lo rechaza).
  useEffect(() => {
    const id = window.setTimeout(() => {
      const guardado = leerGuardado(token);
      if (!guardado) return;
      datos.current = guardado;
      setRetomable(true);
    }, 0);
    return () => clearTimeout(id);
  }, [token]);

  /** Hubo senial de Meta: la ventana existe, no hace falta seguir esperandola. */
  const cancelarEspera = useCallback(() => {
    if (espera.current !== null) {
      clearTimeout(espera.current);
      espera.current = null;
    }
    setSinVentana(false);
  }, []);

  // Que no quede un temporizador vivo si el cliente se va de la pagina.
  useEffect(() => () => cancelarEspera(), [cancelarEspera]);

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

      // Llego algo de Meta: la ventana se abrio.
      cancelarEspera();

      if (cuerpo.event === "FINISH" && cuerpo.data?.waba_id && cuerpo.data?.phone_number_id) {
        datos.current = {
          waba_id: cuerpo.data.waba_id,
          phone_number_id: cuerpo.data.phone_number_id,
        };
        guardarDatos(token, datos.current);
        return;
      }

      // El cliente cerro el popup a mitad de camino. `current_step` dice donde
      // quedo, y sirve para decirle algo mas util que "fallo".
      if (cuerpo.event === "CANCEL") {
        datos.current = null;
        olvidarDatos(token);
        setRetomable(false);
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
  }, [token, cancelarEspera]);

  const finalizar = useCallback(
    async (code: string) => {
      const ids = datos.current ?? leerGuardado(token);
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
      setRetomable(false);
      // Los ids guardados, en cambio, solo se tiran cuando el alta salio bien.
      // Si fallo, siguen siendo los del numero que el cliente eligio y le
      // ahorran rehacer el asistente entero en el proximo intento.
      if (!r.error) olvidarDatos(token);

      setEstado(
        r.error ? { paso: "error", mensaje: r.error } : { paso: "ok", advertencia: r.advertencia },
      );
    },
    [token],
  );

  const abrirPopup = useCallback(() => {
    if (!window.FB || !camino) return;
    setEstado({ paso: "listo" });

    // ★ Si el navegador bloquea la ventana emergente, `FB.login` no llama al
    // callback ni avisa de ninguna manera: el boton parece roto y el cliente se
    // queda mirando una pagina que no reacciona. No hay forma de preguntarle al
    // navegador si la bloqueo -abrir una ventana de prueba para averiguarlo
    // arriesga que la segunda, la que importa, sea la que bloquee-, asi que se
    // mide por lo unico observable: unos segundos sin una sola senial de Meta.
    cancelarEspera();
    espera.current = window.setTimeout(() => setSinVentana(true), 4000);

    window.FB.login(
      (respuesta) => {
        cancelarEspera();
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
        extras: { setup: {}, featureType: FEATURE_TYPE[camino], sessionInfoVersion: "3" },
      },
    );
  }, [camino, configId, finalizar, cancelarEspera]);

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

      {/* La pregunta esta redactada desde lo que el cliente sabe de su propio
          negocio ("uso WhatsApp Business en el celular"), no desde como se
          llama el flujo del lado de Meta: "coexistence" no le dice nada a nadie
          fuera de esta oficina. */}
      <fieldset className="flex flex-col gap-2" disabled={estado.paso === "conectando"}>
        <legend className="mb-1 text-sm font-medium text-zinc-900 dark:text-zinc-100">
          &iquest;Qu&eacute; n&uacute;mero vas a usar?
        </legend>

        <Opcion
          valor="existente"
          elegido={camino}
          alElegir={setCamino}
          titulo="El que ya uso en WhatsApp Business"
          detalle="Seguís contestando desde tu celular como siempre, y el bot atiende en el mismo número. Te va a pedir escanear un código QR, así que tené el celular al lado."
        />

        <Opcion
          valor="nuevo"
          elegido={camino}
          alElegir={setCamino}
          titulo="Un número nuevo, solo para el bot"
          detalle="Para un número que no esté dado de alta en ninguna app de WhatsApp, ni la común ni la Business."
        />
      </fieldset>

      {children}

      <button
        type="button"
        onClick={abrirPopup}
        disabled={!sdkListo || !camino || estado.paso === "conectando"}
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

      {/* Los dos avisos de abajo no son errores: el alta todavia se puede
          terminar. Por eso van en ambar y no en rojo, y por eso dicen que hacer
          en vez de que paso. */}
      {sinVentana && estado.paso !== "conectando" && (
        <p
          role="status"
          className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        >
          &iquest;No se abri&oacute; la ventana de Facebook? Suele ser el bloqueador de ventanas
          emergentes del navegador. Permitilas para esta p&aacute;gina y volv&eacute; a tocar el
          bot&oacute;n.
        </p>
      )}

      {retomable && estado.paso === "listo" && (
        <p
          role="status"
          className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        >
          Ya hab&iacute;as elegido tu n&uacute;mero en un intento anterior, pero el alta no
          lleg&oacute; a terminarse. Volv&eacute; a tocar el bot&oacute;n: el asistente deber&iacute;a
          pasar mucho m&aacute;s r&aacute;pido esta vez.
        </p>
      )}
    </div>
  );
}

/** Una de las dos opciones de alta. Un radio de verdad y no un div con onClick:
 *  esta pagina se abre casi siempre desde el celular. */
function Opcion({
  valor,
  elegido,
  alElegir,
  titulo,
  detalle,
}: {
  valor: Camino;
  elegido: Camino | null;
  alElegir: (c: Camino) => void;
  titulo: string;
  detalle: string;
}) {
  const activo = elegido === valor;
  return (
    <label
      className={`flex cursor-pointer gap-3 rounded-md border p-3 transition-colors ${
        activo
          ? "border-[#1877F2] bg-blue-50 dark:bg-blue-950/40"
          : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-800 dark:hover:border-zinc-700"
      }`}
    >
      <input
        type="radio"
        name="camino-de-alta"
        value={valor}
        checked={activo}
        onChange={() => alElegir(valor)}
        className="mt-1 accent-[#1877F2]"
      />
      <span className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{titulo}</span>
        <span className="text-xs text-zinc-600 dark:text-zinc-400">{detalle}</span>
      </span>
    </label>
  );
}
