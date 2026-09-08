import type { Metadata } from "next";
import { Fraunces, Instrument_Sans } from "next/font/google";

import { GUION_TEMA } from "@/lib/tema";
import "../globals.css";

// El layout raiz de TODO LO QUE VE EL CLIENTE FINAL: la portada, el alta, el
// portal del negocio y los legales.
//
// Ver la nota de app/(panel)/layout.tsx sobre por que hay dos layouts raiz.

const cuerpo = Instrument_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--fuente-cuerpo",
});

// ★ La unica tipografia con personalidad del producto, y esta de este lado a
// proposito: es la cara que ve quien contrata el servicio. En el panel seria
// ruido; aca es lo que hace que el portal no parezca un formulario interno.
// Se usa SOLO en titulos y cifras grandes, nunca en texto corrido.
const titulo = Fraunces({
  subsets: ["latin"],
  weight: ["400", "600"],
  variable: "--fuente-titulo",
});

export const metadata: Metadata = {
  // Lo ve el cliente final en la pestania del navegador cuando abre su portal,
  // asi que no puede seguir diciendo "demo".
  title: { default: "ArgencoreAI", template: "%s · ArgencoreAI" },
  description: "Asistente de WhatsApp para tu negocio.",
};

export default function LayoutPublico({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="es"
      data-piel="papel"
      // Los datos de este lado -horas, contadores- van en la misma familia que
      // el cuerpo: no hay monoespaciada en el portal, porque a quien lo abre no
      // le sirve que su ultima conversacion parezca una salida de consola.
      className={`${cuerpo.variable} ${titulo.variable} [--fuente-datos:var(--fuente-cuerpo)] h-full`}
      suppressHydrationWarning
    >
      <body className="flex min-h-full flex-col bg-fondo text-texto">
        <script dangerouslySetInnerHTML={{ __html: GUION_TEMA }} />
        {children}
      </body>
    </html>
  );
}
