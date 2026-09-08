// El contrato del tema claro/oscuro. Sin "use client" a proposito: lo importan
// los dos layouts raiz, que son componentes de servidor.
//
// El tema tiene TRES estados y no dos. "Oscuro" y "claro" son elecciones de la
// persona; el tercero -y el que viene por defecto- es no haber elegido, y ahi
// manda el sistema operativo. Un interruptor de dos posiciones obliga a elegir
// en la primera visita y despues no deja volver.

export const CLAVE_TEMA = "argencore:tema";

/** Los tres estados. `sistema` no escribe nada en el documento. */
export type Tema = "sistema" | "claro" | "oscuro";

/**
 * El guion que corre ANTES de que el navegador pinte.
 *
 * ★ POR QUE INLINE Y NO UN useEffect
 * Un efecto corre despues del primer pintado: quien eligio oscuro veria un
 * fogonazo blanco en cada navegacion. Esto se ejecuta sincronicamente al
 * principio del <body>, asi que el atributo ya esta puesto cuando se pinta la
 * primera linea.
 *
 * Va envuelto en try/catch porque `localStorage` LEVANTA -no devuelve null- en
 * una ventana privada o con las cookies bloqueadas. Sin el catch, esa excepcion
 * corta el guion y se lleva puesto el resto de la pagina.
 */
export const GUION_TEMA = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  CLAVE_TEMA,
)});if(t==="claro"||t==="oscuro"){document.documentElement.setAttribute("data-tema",t)}}catch(e){}})()`;
