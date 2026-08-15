// Clases compartidas entre paginas de servidor y componentes de cliente.
//
// ★ Este archivo NO lleva "use client" a proposito.
//
// Un valor exportado desde un modulo marcado con "use client" no llega al
// servidor como el valor real: Next lo reemplaza por una referencia al cliente.
// Al interpolarlo en un template string (`mt-1 ${claseInput}`) se stringifica
// esa referencia y el className termina siendo basura -los campos quedan sin
// ningun estilo-. TypeScript no lo detecta porque el tipo declarado sigue
// siendo `string`; solo se ve abriendo la pagina.
const CAMPO =
  "rounded-md border border-zinc-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700";

export const claseInput = `w-full ${CAMPO}`;

/**
 * Para campos que tienen que medir lo que mide su contenido, como el desplegable
 * de "cuantas horas".
 *
 * ★ No alcanza con escribir `${claseInput} w-auto`: Tailwind resuelve el empate
 * entre dos utilidades de width por el orden en la hoja de estilos, no por el
 * orden en el atributo class. `w-full` gana igual y el desplegable termina
 * ocupando todo el ancho de la tarjeta. Por eso la variante angosta se arma
 * sacando `w-full`, no agregandole otra clase encima.
 */
export const claseCampoAngosto = CAMPO;
