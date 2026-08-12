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

      <ul className="mt-4 mb-5 list-disc space-y-1 pl-5 text-sm text-zinc-500">
        <li>Us&aacute; un n&uacute;mero que no est&eacute; activo en la app de WhatsApp comun.</li>
        <li>Ten&eacute; a mano el tel&eacute;fono: Facebook te manda un c&oacute;digo.</li>
        <li>No cierres la ventana hasta que termine.</li>
      </ul>

      <BotonConectar
        token={token}
        appId={estado.app_id}
        configId={estado.config_id}
        apiVersion={estado.api_version}
      />
    </Marco>
  );
}
