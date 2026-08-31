import Link from "next/link";

import { ACTUALIZADO, EMPRESA } from "@/lib/empresa";

// Grupo de rutas (legal): las tres paginas comparten marco y pie, pero cada una
// vive en su propia URL porque Meta pide una URL distinta para cada documento.
//
// A diferencia del panel y del onboarding, estas paginas SI son publicas e
// indexables: Meta las revisa desde afuera y tienen que abrir sin sesion.

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 bg-white px-4 py-12 dark:bg-black">
      <div className="mx-auto w-full max-w-2xl">
        <article
          className="text-sm leading-relaxed text-texto
            [&_a]:underline
            [&_h1]:mb-1 [&_h1]:text-2xl [&_h1]:font-semibold [&_h1]:text-texto
            [&_h2]:mt-8 [&_h2]:mb-2 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-texto
            [&_li]:mb-1
            [&_p]:mb-3
            [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-5"
        >
          {children}
        </article>

        <footer className="mt-12 border-t border-borde pt-6 text-xs text-texto-suave dark:border-borde">
          <p className="mb-2">Ultima actualizacion: {ACTUALIZADO}</p>
          <nav className="flex flex-wrap gap-x-4 gap-y-1">
            <Link href="/privacidad" className="hover:underline">
              Politica de privacidad
            </Link>
            <Link href="/terminos" className="hover:underline">
              Terminos del servicio
            </Link>
            <Link href="/eliminar-datos" className="hover:underline">
              Eliminacion de datos
            </Link>
          </nav>
          <p className="mt-3">
            {EMPRESA.nombreComercial} &middot;{" "}
            <a href={`mailto:${EMPRESA.email}`} className="hover:underline">
              {EMPRESA.email}
            </a>
          </p>
        </footer>
      </div>
    </div>
  );
}
