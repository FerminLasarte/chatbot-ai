"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

// Mantiene la pantalla al dia sin que nadie recargue.
//
// ★ POR QUE `router.refresh()` Y NO SSE NI WEBSOCKETS
// Lo que hay que resolver es "si alguien empezo a esperar, que aparezca solo".
// Eso tolera perfectamente veinte segundos de retraso, y `refresh()` vuelve a
// correr el componente de servidor y fusiona el resultado SIN perder el estado
// de cliente: el panel lateral que estaba abierto sigue abierto y lo que
// alguien estaba escribiendo sigue escrito. Un canal permanente seria otra
// pieza de infraestructura -y otra cosa que se puede caer en silencio- para
// ganar unos segundos que a nadie le cambian el dia.
//
// Las llamadas de lib/api.ts van con `cache: "no-store"`, asi que cada refresco
// trae datos frescos de verdad y no una copia del cache.

/** Cada cuanto se refresca mientras la pestania esta a la vista. */
const SEGUNDOS = 20;

export function EnVivo() {
  const router = useRouter();
  const [activo, setActivo] = useState(true);

  useEffect(() => {
    if (!activo) return;

    // ★ No se refresca con la pestania escondida. Sin esto, una pestania
    // olvidada en el fondo del navegador le pega a la API cada veinte segundos
    // durante todo el fin de semana, y con ella a la base.
    const tic = () => {
      if (!document.hidden) router.refresh();
    };

    const id = window.setInterval(tic, SEGUNDOS * 1000);

    // Al volver a la pestania se refresca en el acto: quien vuelve despues de
    // un rato no tiene por que mirar datos viejos hasta el proximo tic.
    const alVolver = () => {
      if (!document.hidden) router.refresh();
    };
    document.addEventListener("visibilitychange", alVolver);

    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", alVolver);
    };
  }, [router, activo]);

  return (
    <button
      type="button"
      onClick={() => setActivo((a) => !a)}
      title={
        activo
          ? `Se actualiza solo cada ${SEGUNDOS} segundos. Tocá para pausar.`
          : "Actualización automática en pausa. Tocá para reanudar."
      }
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] text-texto-tenue transition-colors hover:bg-superficie-2 hover:text-texto-suave"
    >
      <span
        className={`size-1.5 rounded-full ${
          activo ? "animate-pulse bg-ok" : "bg-texto-tenue"
        }`}
      />
      {activo ? "En vivo" : "Pausado"}
    </button>
  );
}
