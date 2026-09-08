import { notFound } from "next/navigation";

import { Demo } from "./demo";

export const metadata = {
  title: "Probar el asistente",
  robots: { index: false, follow: false },
};

/**
 * El portero de la pantalla de prueba: existe en desarrollo y no en el sitio
 * desplegado.
 *
 * ★ POR QUE `NODE_ENV` Y NO UNA VARIABLE DE ENTORNO PROPIA
 * `next build` corre siempre con `NODE_ENV=production`, asi que esto es cierto
 * por construccion en la imagen de Railway y falso con `npm run dev`. No hay
 * variable que alguien pueda prender por error ni olvidarse de apagar; para
 * publicar esta pantalla hay que venir a este archivo a proposito.
 *
 * ★ ESTE PORTERO NO PROTEGE LA CLAVE, PROTEGE LA PANTALLA
 * Una variable `NEXT_PUBLIC_*` se incrusta en el JavaScript DURANTE EL BUILD,
 * asi que si alguien la carga al construir la imagen, la clave viaja en el
 * bundle aunque esta ruta devuelva 404 y nadie pueda usarla. Comprobado
 * grepeando `.next/static` con y sin la variable.
 *
 * Lo que de verdad impide eso es que el `Dockerfile` ya no acepte esos build
 * args, mas la advertencia en `docs/deploy.md`. Si algun dia alguien se los
 * devuelve al Dockerfile, este 404 no lo va a salvar.
 *
 * ★ QUE HAY QUE HACER EL DIA QUE SE QUIERA PUBLICAR
 * Sacar estas dos lineas NO alcanza. Hoy el flujo pide una clave con scope
 * `tenant`, que **puede subir documentos**. Antes de publicarla hay que pasarla
 * a una con scope `chat` -que solo conversa- apuntando a un tenant de demo.
 * Los tres pasos estan en docs/deploy.md.
 */
export default function Probar() {
  if (process.env.NODE_ENV === "production") notFound();

  return <Demo />;
}
