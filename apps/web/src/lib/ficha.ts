// La ficha de datos del negocio, del lado del navegador.
//
// ★ SIN "server-only", AL REVES QUE lib/api.ts Y lib/portal.ts
// Aquellos llevan credenciales y no pueden cruzar al navegador nunca. Esto es
// la FORMA del dato y el nombre de los dias: lo necesitan las dos Server
// Actions -que corren en el servidor- y tambien el formulario, que corre en el
// navegador. No hay nada secreto que proteger.
//
// ★ POR QUE EL FORMULARIO MANDA CAMPOS NATIVOS Y NO UN JSON ESCONDIDO
// La alternativa era guardar la ficha entera en estado de React y mandarla en
// un `<input type="hidden">` con JSON adentro. Con campos nativos, la
// validacion del navegador (`required`, el formato de la hora) funciona sola,
// el formulario anda aunque falle el JS, y `CampoDeHora` se usa como fue
// disenado: con `name` y `defaultValue`, sin estado.
//
// El precio es este archivo: alguien tiene que volver a armar la ficha desde el
// FormData. Se hace UNA vez, aca, y lo usan las dos puertas.

/** 0 = lunes ... 6 = domingo. Igual que en la API: el indice ES el dia. */
export const DIAS = [
  "lunes",
  "martes",
  "miércoles",
  "jueves",
  "viernes",
  "sábado",
  "domingo",
] as const;

/** Los mismos topes que valida la API (`app/schemas/negocio.py`).
 *
 *  ★ Estan repetidos a proposito, y la API sigue siendo la que manda: aca solo
 *  sirven para que el formulario no OFREZCA lo que despues va a ser rechazado.
 *  Un boton "agregar" que produce un 422 es peor que no tenerlo. */
export const MAX_TRAMOS_POR_DIA = 3;
export const MAX_EXTRAS = 10;

export type TramoHorario = { dia: number; desde: string; hasta: string };
export type BloqueExtra = { titulo: string; texto: string };

/** Es el `FichaNegocio` de la API, tal cual viaja. */
export type Ficha = {
  direccion: string | null;
  horarios: TramoHorario[];
  envios: string | null;
  medios_de_pago: string | null;
  web_y_redes: string | null;
  no_hacemos: string | null;
  extras: BloqueExtra[];
};

export const FICHA_VACIA: Ficha = {
  direccion: null,
  horarios: [],
  envios: null,
  medios_de_pago: null,
  web_y_redes: null,
  no_hacemos: null,
  extras: [],
};

/** Los campos de texto sueltos, en el orden en que se muestran. */
export const CAMPOS_DE_TEXTO = [
  "direccion",
  "envios",
  "medios_de_pago",
  "web_y_redes",
  "no_hacemos",
] as const;

/** "09:00:00" -> "09:00".
 *
 *  La API serializa las horas con segundos. Un `<input type="time">` con
 *  `step=60` los ignora al mostrarlos, pero no todos los navegadores hacen lo
 *  mismo con un `defaultValue` que los trae: algunos muestran el campo vacio. */
export function hhmm(hora: string): string {
  return hora.slice(0, 5);
}

/**
 * Rearma la ficha desde lo que mando el formulario.
 *
 * Los tramos y los bloques viajan como campos REPETIDOS (`tramo_dia`,
 * `tramo_desde`, ...) y se emparejan por posicion: el formulario los dibuja
 * siempre en el mismo orden, asi que la n-esima hora de inicio corresponde a la
 * n-esima hora de fin. Es lo que permite que agregar y quitar filas sea puro
 * DOM, sin indices escritos en los `name`.
 *
 * ★ Esto NO valida: valida la API, que es la unica que no se puede saltear (una
 * Server Action es un endpoint HTTP y le puede llegar cualquier FormData). Aca
 * solo se descartan las filas incompletas, que son las que produce el propio
 * formulario cuando alguien agrega una y la deja a medio llenar.
 */
export function fichaDesdeFormulario(form: FormData): Ficha {
  const texto = (campo: string): string | null => {
    const v = String(form.get(campo) ?? "").trim();
    return v || null;
  };

  const dias = form.getAll("tramo_dia").map(String);
  const desdes = form.getAll("tramo_desde").map(String);
  const hastas = form.getAll("tramo_hasta").map(String);

  const horarios: TramoHorario[] = dias
    .map((dia, i) => ({
      dia: Number(dia),
      desde: desdes[i] ?? "",
      hasta: hastas[i] ?? "",
    }))
    .filter((t) => Number.isInteger(t.dia) && t.desde !== "" && t.hasta !== "");

  const titulos = form.getAll("extra_titulo").map(String);
  const textos = form.getAll("extra_texto").map(String);

  const extras: BloqueExtra[] = titulos
    .map((titulo, i) => ({ titulo: titulo.trim(), texto: (textos[i] ?? "").trim() }))
    .filter((b) => b.titulo !== "" && b.texto !== "");

  return {
    direccion: texto("direccion"),
    horarios,
    envios: texto("envios"),
    medios_de_pago: texto("medios_de_pago"),
    web_y_redes: texto("web_y_redes"),
    no_hacemos: texto("no_hacemos"),
    extras,
  };
}
