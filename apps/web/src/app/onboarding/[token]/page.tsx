import { ErrorOnboarding, verEstadoOnboarding } from "@/lib/onboarding";
import { BotonConectar } from "./conectar";

// Esta pagina la abre el cliente de la agencia, no la agencia. Es la unica del
// proyecto que vive fuera de /panel y no pide login: la credencial es el token
// del link (ver lib/onboarding.ts).
export const metadata = {
  title: "Conectar WhatsApp",
  // Un link con token no tiene por que terminar indexado en Google.
  robots: { index: false, follow: false },
};

function Marco({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-1 items-center justify-center bg-zinc-50 px-4 py-10 dark:bg-black">
      <div className="w-full max-w-md rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        {children}
      </div>
    </div>
  );
}

export default async function Onboarding({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;

  let estado;
  try {
    estado = await verEstadoOnboarding(token);
  } catch (e) {
    // El error se muestra, no se convierte en un 404 generico: quien abre esto
    // es alguien no tecnico que necesita saber si tiene que pedir otro link o
    // avisarle a la agencia.
    const mensaje =
      e instanceof ErrorOnboarding
        ? e.message
        : "No se pudo abrir esta pagina. Proba de nuevo en un rato.";
    return (
      <Marco>
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Este link no se puede usar
        </h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{mensaje}</p>
      </Marco>
    );
  }

  if (estado.ya_conectado) {
    return (
      <Marco>
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          {estado.nombre_cliente}
        </h1>
        <p className="mt-2 rounded-md bg-green-50 px-3 py-2 text-sm text-green-700 dark:bg-green-950 dark:text-green-300">
          Tu WhatsApp ya est&aacute; conectado. No hace falta que hagas nada.
        </p>
      </Marco>
    );
  }

  return (
    <Marco>
      <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
        Conect&aacute; tu WhatsApp
      </h1>
      <p className="mt-1 text-sm text-zinc-500">{estado.nombre_cliente}</p>

      <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
        Al tocar el bot&oacute;n se abre una ventana de Facebook. Ah&iacute; entr&aacute;s con la
        cuenta de tu negocio y eleg&iacute;s el n&uacute;mero de tel&eacute;fono que va a usar el
        asistente. Son un par de minutos y no hace falta configurar nada m&aacute;s.
      </p>

      {/* Solo lo que vale para los DOS caminos de alta. Lo que cambia segun el
          camino (que el numero no este en ninguna app, o que haya que escanear
          un QR) va en la opcion que corresponde, adentro de BotonConectar: una
          instruccion suelta aca arriba que contradiga a la opcion elegida es
          peor que no ponerla. */}
      <ul className="mt-4 mb-5 list-disc space-y-1 pl-5 text-sm text-zinc-500">
        <li>Ten&eacute; el tel&eacute;fono a mano: te va a pedir confirmar el n&uacute;mero.</li>
        <li>No cierres la ventana hasta que termine.</li>
      </ul>

      <BotonConectar
        token={token}
        appId={estado.app_id}
        configId={estado.config_id}
        apiVersion={estado.api_version}
      >
        {/* Va como children para que quede pegado al boton, despues de la
            eleccion del numero. Meta mira esta pantalla en la revision de la
            app, y ademas es lo justo: antes de conectar su WhatsApp el cliente
            tiene que poder leer que hacemos con los datos. */}
        <p className="text-xs text-zinc-500">
          Al conectar acept&aacute;s nuestros{" "}
          <a href="/terminos" className="underline">
            t&eacute;rminos
          </a>{" "}
          y la{" "}
          <a href="/privacidad" className="underline">
            pol&iacute;tica de privacidad
          </a>
          .
        </p>
      </BotonConectar>
    </Marco>
  );
}
