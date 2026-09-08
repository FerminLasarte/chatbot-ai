/**
 * Minutos -> texto corto ("40 min", "2 h 15 min", "5 h", "3 d").
 *
 * Solo formatea: los minutos vienen calculados de la API. El panel y el portal
 * del cliente se renderizan en el servidor (Railway, en UTC), asi que si
 * restaran fechas por su cuenta mostrarian horas que no son las de quien esta
 * mirando. Ver el comentario de `Conversacion` en lib/api.ts.
 *
 * ★ LA PRECISION BAJA CON LA ANTIGUEDAD, A PROPOSITO
 * A los cinco minutos, los minutos importan: "hace 3 min" y "hace 40 min" son
 * dos situaciones distintas para quien mira quien esta esperando. A las seis
 * horas ya no cambian nada, y "hace 6 h 13 min" es ruido en un chip que se lee
 * de reojo -y un numero que se mueve cada minuto en una pantalla que ahora se
 * refresca sola-. Desde las 3 h se redondea a la hora.
 *
 * Sin "use client" a proposito: lo usan paginas de servidor. Ver la nota de
 * components/ui.tsx sobre por que eso importa.
 */

/** Desde aca en adelante los minutos sueltos ya no aportan nada. */
const HORAS_SIN_MINUTOS = 3;

export function duracion(minutos: number): string {
  if (minutos < 60) return `${minutos} min`;

  const horas = Math.floor(minutos / 60);

  if (horas < 24) {
    const resto = minutos % 60;
    if (resto === 0 || horas >= HORAS_SIN_MINUTOS) return `${horas} h`;
    return `${horas} h ${resto} min`;
  }

  return `${Math.floor(horas / 24)} d`;
}
