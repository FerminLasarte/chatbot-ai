/**
 * Minutos -> texto corto ("40 min", "2 h 15 min", "3 d").
 *
 * Solo formatea: los minutos vienen calculados de la API. El panel y el portal
 * del cliente se renderizan en el servidor (Railway, en UTC), asi que si
 * restaran fechas por su cuenta mostrarian horas que no son las de quien esta
 * mirando. Ver el comentario de `Conversacion` en lib/api.ts.
 *
 * Sin "use client" a proposito: lo usan paginas de servidor. Ver la nota de
 * lib/estilos.ts sobre por que eso importa.
 */
export function duracion(minutos: number): string {
  if (minutos < 60) return `${minutos} min`;

  const horas = Math.floor(minutos / 60);
  if (horas < 24) {
    const resto = minutos % 60;
    return resto === 0 ? `${horas} h` : `${horas} h ${resto} min`;
  }
  return `${Math.floor(horas / 24)} d`;
}
