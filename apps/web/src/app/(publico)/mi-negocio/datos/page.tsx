import { CamposDeLaFicha } from "@/components/ficha-del-negocio";
import { AccesoRevocado, listarMisConversaciones, verMiFicha, verMiNegocio } from "@/lib/portal";
import { cuantasEsperan } from "@/lib/conversaciones";
import { claveDelPortal } from "@/lib/sesion-portal";
import { guardarMiFicha } from "../acciones";
import { EncabezadoDelPortal, Marco, SinAcceso } from "../marco";
import { Boton, FormularioPortal } from "../ui";

export const metadata = {
  title: "Mi negocio",
  robots: { index: false, follow: false },
};

/**
 * Los datos del negocio, editados por su duenio.
 *
 * ★ ESTA ES LA PANTALLA QUE JUSTIFICA TODO EL PUNTO 1 DE LA HOJA DE RUTA.
 * Antes, cambiar un horario de verano era un pedido de soporte para la agencia:
 * el dato vivia en el prompt, que solo se edita del otro lado. Acá lo corrige
 * quien lo sabe, y el asistente lo usa en la respuesta siguiente.
 *
 * Lo que el duenio NO toca sigue siendo lo mismo: el prompt, los documentos y
 * las claves. Esto son DATOS que el asistente cita, no instrucciones (ver
 * `ai/prompts/negocio.py` del lado de la API).
 */
export default async function DatosDelNegocio() {
  const clave = await claveDelPortal();

  if (!clave) {
    return (
      <SinAcceso
        titulo="Entrá con tu link"
        detalle="Para ver los datos de tu negocio abrí el link que te pasaron por mail o WhatsApp. Guardalo en favoritos: sirve todas las veces que quieras."
      />
    );
  }

  let negocio;
  let ficha;
  let conversaciones;
  try {
    // Las tres son independientes: en serie sumarian sus latencias. Las
    // conversaciones se piden solo para el contador del nav —que alguien esté
    // esperando es lo único que puede pasar mientras se editan los horarios—.
    [negocio, ficha, conversaciones] = await Promise.all([
      verMiNegocio(clave),
      verMiFicha(clave),
      listarMisConversaciones(clave),
    ]);
  } catch (e) {
    if (e instanceof AccesoRevocado) {
      return (
        <SinAcceso
          titulo="Tu acceso fue dado de baja"
          detalle="El link con el que entraste ya no tiene permiso. Pedile uno nuevo a quien te lo pasó."
        />
      );
    }
    return (
      <SinAcceso
        titulo="No pudimos cargar tus datos"
        detalle="Fue un problema nuestro. Probá de nuevo en unos minutos."
      />
    );
  }

  return (
    <Marco>
      <EncabezadoDelPortal
        nombre={negocio.nombre}
        esperando={cuantasEsperan(conversaciones)}
        estado="Esto es lo que tu asistente sabe del negocio. Lo que cambies acá lo usa en la próxima respuesta."
      />

      <FormularioPortal accion={guardarMiFicha} className="flex flex-col gap-6">
        <CamposDeLaFicha ficha={ficha} />

        <div className="flex items-center gap-3">
          <Boton>Guardar los datos</Boton>
          <span className="text-xs text-texto-tenue">No hace falta avisarle a nadie.</span>
        </div>
      </FormularioPortal>
    </Marco>
  );
}
