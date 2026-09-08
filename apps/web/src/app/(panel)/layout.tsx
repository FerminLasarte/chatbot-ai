import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

import { GUION_TEMA } from "@/lib/tema";
import "../globals.css";

// El layout raiz del PANEL DE LA AGENCIA.
//
// ★ POR QUE HAY DOS LAYOUTS RAIZ Y NO UNO
// El panel y las pantallas del cliente final son dos pieles distintas del
// mismo sistema (ver globals.css). Con un solo layout, `data-piel` habria que
// ponerlo en un div de adentro, y entonces: el fondo del <body> quedaria de la
// otra piel -se ve al hacer rebote de scroll-, y CADA pantalla del producto
// descargaria las cuatro tipografias en vez de las dos que usa.
//
// Con un layout raiz por grupo de rutas, `data-piel` es un atributo estatico
// del <html>: no parpadea, no necesita JavaScript, y cada lado carga lo suyo.
// Los grupos entre parentesis no aparecen en la URL: /panel sigue siendo /panel.

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--fuente-cuerpo",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--fuente-datos",
});

export const metadata: Metadata = {
  title: { default: "Panel", template: "%s · Panel" },
  // El panel no se indexa: es una pantalla con contrasenia compartida.
  robots: { index: false, follow: false },
};

export default function LayoutDelPanel({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="es"
      data-piel="consola"
      // La consola no tiene tipografia de titulo aparte: la jerarquia la hace
      // el peso y el tracking de la misma familia, que es lo que la mantiene
      // parecida a un instrumento y no a una revista.
      className={`${plexSans.variable} ${plexMono.variable} [--fuente-titulo:var(--fuente-cuerpo)] h-full`}
      // El servidor no sabe que tema eligio esta persona, asi que la primera
      // pintura puede diferir de lo que el guion de abajo deja puesto.
      suppressHydrationWarning
    >
      {/* ★ EN <head> Y NO EN <body>, y con dangerouslySetInnerHTML.
          Es el patron que documenta Next para esto (guides/preventing-flash-
          before-hydration): el navegador lo ejecuta sincronicamente mientras
          parsea el head, o sea antes de pintar la primera linea. Adentro del
          body React avisa -con razon- que un <script> renderizado por el no se
          ejecuta en las navegaciones del lado del cliente. */}
      <head>
        <script dangerouslySetInnerHTML={{ __html: GUION_TEMA }} />
      </head>
      <body className="flex min-h-full flex-col bg-fondo text-texto">
        {children}
      </body>
    </html>
  );
}
