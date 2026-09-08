import Link from "next/link";

import { InterruptorDeTema } from "@/components/tema";
import { EMPRESA } from "@/lib/empresa";

export const metadata = {
  title: "Argencore · Asistente de WhatsApp para comercios",
  description:
    "Un asistente que contesta las consultas de tus clientes por WhatsApp, con la información de tu negocio.",
};

// La raiz del dominio.
//
// ★ QUE HABIA ACA ANTES
// El chat de prueba del motor, con una zona para arrastrar un PDF y un cartel
// que decia "Falta NEXT_PUBLIC_API_KEY... corre este comando". Era una
// herramienta de desarrollo que quedo ocupando la puerta de entrada: cualquiera
// que abriera el dominio -un cliente al que le pasas el link- veia un chat de
// laboratorio y un error de programador. Ahora vive en /probar y solo en
// desarrollo.
//
// ★ POR QUE ESTA PAGINA ES CORTA A PROPOSITO
// No es una landing de venta: eso se escribe cuando haya algo que vender por
// autoservicio. Hoy el producto se vende hablando, y esta URL cumple tres
// funciones concretas: decir de quien es el sitio, dejar entrar al equipo, y
// tener las tres paginas legales a un click -que es lo que Meta revisa desde
// afuera, y hasta ahora solo se linkeaban desde el alta-.

export default function Portada() {
  return (
    <div className="flex flex-1 flex-col px-4 py-10 sm:py-16">
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-10">
        <header className="flex items-start justify-between gap-4">
          <p className="font-titulo text-sm font-semibold tracking-tight text-texto">
            {EMPRESA.nombreComercial}
          </p>
          <InterruptorDeTema />
        </header>

        <main className="flex flex-1 flex-col justify-center gap-6 py-6">
          <div>
            <h1 className="font-titulo text-3xl font-semibold tracking-tight text-balance text-texto sm:text-4xl">
              Un asistente que atiende tu WhatsApp
            </h1>
            <p className="mt-3 max-w-prose text-base text-texto-suave">
              Contesta las consultas de tus clientes con la informaci&oacute;n de tu negocio
              &mdash;horarios, precios, env&iacute;os&mdash; y te avisa cuando alguien
              necesita hablar con una persona. Vos segu&iacute;s contestando desde el mismo
              WhatsApp de siempre cuando quer&eacute;s.
            </p>
          </div>

          {/* ★ ACA NO VA UN LINK AL PANEL, y estuvo un rato. Esta es la
              puerta publica: un cliente al que se le manda el dominio, o Meta
              revisando la app, no tienen nada que hacer en una herramienta
              interna, y publicarla le dice a cualquiera donde esta la puerta.
              El login tiene una contrasena fuerte pero NO tiene bloqueo por
              intentos fallidos: solo una espera de 700 ms. Quien necesita el
              panel lo tiene en favoritos. */}
          <div className="text-sm">
            <a
              href={`mailto:${EMPRESA.email}`}
              className="font-medium text-acento hover:underline"
            >
              Escribinos
            </a>
          </div>
        </main>

        <footer className="border-t border-borde pt-6 text-xs text-texto-suave">
          <nav className="flex flex-wrap gap-x-4 gap-y-1">
            <Link href="/privacidad" className="hover:underline">
              Pol&iacute;tica de privacidad
            </Link>
            <Link href="/terminos" className="hover:underline">
              T&eacute;rminos del servicio
            </Link>
            <Link href="/eliminar-datos" className="hover:underline">
              Eliminaci&oacute;n de datos
            </Link>
          </nav>
          <p className="mt-3">
            {EMPRESA.razonSocial} &middot;{" "}
            <a href={`mailto:${EMPRESA.email}`} className="hover:underline">
              {EMPRESA.email}
            </a>
          </p>
        </footer>
      </div>
    </div>
  );
}
