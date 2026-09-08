"use client";

import { IconoCerrar, IconoMas } from "@/components/iconos";
import { claseBoton } from "@/components/ui";

// Una lista a la que se le agregan y se le quitan filas.
//
// ★ POR QUE EXISTE ANTES QUE LA PANTALLA QUE LA USA
// La ficha del negocio la va a necesitar dos veces -los tramos de horario y los
// bloques extra- y son dos usos bastante distintos: uno son tres campos chicos
// en una linea, el otro un titulo y un textarea. Si no existe la pieza, cada
// uno se la inventa, y despues el boton de quitar esta en un lugar distinto en
// cada una. Es el mismo error de los dos grises, pero en el layout.
//
// ★ ES PRESENTACIONAL: NO GUARDA LAS FILAS
// El estado vive arriba, en quien conoce la forma de los datos. Aca solo esta
// como se ven una lista que crece, su boton de agregar y su boton de quitar.
//
// ★ "use client" A PROPOSITO, aunque no tenga estado
// Recibe `alAgregar` y `alQuitar`, que son funciones, asi que solo puede
// montarse dentro de un arbol de cliente. Marcarlo lo vuelve explicito: si
// alguien lo importara desde una pagina de servidor, falla al importar y no en
// runtime con un onClick que nunca se dispara.

export function Repetible({
  children,
  alAgregar,
  etiquetaAgregar,
  /** Cuantas se pueden cargar como maximo. Al llegar, el boton se va y se dice
   *  por que: un boton que no hace nada es peor que ningun boton. */
  maximo,
  cuantas,
  /** Que decir cuando todavia no hay ninguna. Nunca "sin datos": esto es un
   *  formulario por llenar, no una pantalla rota. */
  vacio,
}: {
  children: React.ReactNode;
  alAgregar: () => void;
  etiquetaAgregar: string;
  maximo?: number;
  cuantas: number;
  vacio?: string;
}) {
  const lleno = maximo !== undefined && cuantas >= maximo;

  return (
    <div className="flex flex-col gap-2">
      {cuantas === 0 && vacio && <p className="text-sm text-texto-suave">{vacio}</p>}

      {cuantas > 0 && <div className="flex flex-col gap-2">{children}</div>}

      {lleno ? (
        <p className="text-xs text-texto-tenue">
          Llegaste al m&aacute;ximo de {maximo}. Para agregar otro, quit&aacute; alguno de
          arriba.
        </p>
      ) : (
        <div>
          <button type="button" onClick={alAgregar} className={claseBoton("suave", "chico")}>
            <IconoMas className="size-3.5" />
            {etiquetaAgregar}
          </button>
        </div>
      )}
    </div>
  );
}

/** Una fila de la lista: lo que sea que le pongan adentro, y como sacarla.
 *
 *  ★ El boton de quitar lleva `aria-label` obligatorio y con el nombre de lo
 *  que quita ("Quitar el tramo de las 9:00"). Diez botones seguidos que dicen
 *  todos "Quitar" son inservibles con un lector de pantalla, que es la unica
 *  forma que tiene alguien de saber cual de los diez esta por tocar. */
export function FilaRepetible({
  children,
  alQuitar,
  etiquetaQuitar,
  /** Los campos arriba y el boton al costado, o todo en una linea. `bloque` es
   *  para filas altas -un titulo y un textarea-; `linea` para filas de campos
   *  chicos, como un tramo de horario. */
  forma = "linea",
}: {
  children: React.ReactNode;
  alQuitar: () => void;
  etiquetaQuitar: string;
  forma?: "linea" | "bloque";
}) {
  return (
    <div
      className={`flex gap-2 ${
        forma === "linea" ? "flex-wrap items-center" : "items-start"
      }`}
    >
      <div className={forma === "linea" ? "flex flex-wrap items-center gap-2" : "min-w-0 flex-1"}>
        {children}
      </div>

      <button
        type="button"
        onClick={alQuitar}
        aria-label={etiquetaQuitar}
        title={etiquetaQuitar}
        className="shrink-0 rounded-control p-1.5 text-texto-tenue transition-colors hover:bg-error-suave hover:text-error"
      >
        <IconoCerrar className="size-3.5" />
      </button>
    </div>
  );
}
