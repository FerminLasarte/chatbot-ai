import { NextResponse } from "next/server";

import { AccesoRevocado, ErrorPortal, verMiNegocio } from "@/lib/portal";
import { guardarClaveDelPortal } from "@/lib/sesion-portal";

// La puerta de entrada del portal: el cliente abre el link que le mando la
// agencia, y esto lo cambia por una sesion.
//
// ★ POR QUE ES UN ROUTE HANDLER Y NO UNA PAGINA
// Next no deja escribir cookies mientras se renderiza un Server Component (ya
// empezo a mandar el HTML: no quedan headers por escribir). Guardar la cookie
// tiene que pasar antes, en un handler o en una server action. Aca ademas es lo
// que queremos: no se dibuja nada en esta URL, se canjea el token y se redirige.
//
// ★ POR QUE LA REDIRECCION IMPORTA
// El link lleva la clave en la URL, asi que despues de esta visita queda en el
// historial del navegador y en los logs de acceso de cualquier proxy. Al
// redirigir a /mi-negocio -sin la clave-, todo lo que el cliente haga a partir
// de ahi (recargar, navegar, compartir la pantalla) ya no la expone. El link
// original le sigue sirviendo para volver a entrar desde otro dispositivo.

export async function GET(
  request: Request,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;
  const destino = new URL("/mi-negocio", request.url);

  try {
    // Se valida ANTES de guardar la cookie. Si no, un link viejo o mal copiado
    // dejaria una cookie invalida que rompe la pagina en cada visita siguiente,
    // y el cliente no tendria como salir de ese estado.
    await verMiNegocio(token);
  } catch (e) {
    // Se distingue "el link no sirve" de "el servidor no contesta" porque lo
    // que tiene que hacer el cliente es distinto: en un caso pedir otro link,
    // en el otro volver a intentar en un rato. Un unico mensaje generico manda
    // a la mitad de la gente a molestar a la agencia por una caida pasajera.
    const invalido = e instanceof AccesoRevocado || (e instanceof ErrorPortal && e.status === 404);
    destino.searchParams.set("link", invalido ? "invalido" : "error");
    return NextResponse.redirect(destino);
  }

  await guardarClaveDelPortal(token);
  return NextResponse.redirect(destino);
}
