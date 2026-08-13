// Datos de la empresa que aparecen en las paginas legales.
//
// Estan aca y no repetidos en cada pagina porque Meta, y cualquier cliente que
// lea los terminos, esperan que los tres documentos digan exactamente lo mismo.
// Si estos datos viven en tres archivos, tarde o temprano dicen tres cosas.
//
// Se opera como persona fisica, no como sociedad: el titular es quien responde,
// y por eso figura su nombre y no una razon social de empresa. Es valido —una
// persona fisica con CUIT es parte legal suficiente para prestar el servicio—,
// pero si algun dia se constituye una SRL o SA hay que cambiar los tres campos
// de abajo y volver a desplegar. Nada mas depende de esto.
export const EMPRESA = {
  nombreComercial: "Argencore",
  // Tiene que coincidir EXACTO con lo que figura en ARCA, incluidos los acentos:
  // es el dato que Meta contrasta contra la documentacion en la verificacion.
  razonSocial: "Fermin Lasarte",
  cuit: "20-43448133-4",
  // Tambien es el que va cargado en la verificacion de empresa de Meta: si los
  // dos no coinciden, la verificacion se rechaza.
  domicilio: "Brasil 219, Tandil, Provincia de Buenos Aires, Argentina",
  email: "argencoresolutions@gmail.com",
  // El servicio que prestamos, dicho igual en los tres documentos.
  servicio: "un asistente automatico que responde consultas por WhatsApp en nombre de empresas",
} as const;

// Fecha de ultima actualizacion de los tres documentos. Se cambia a mano cuando
// se edita alguno: es un dato legal, no la fecha del build.
export const ACTUALIZADO = "13 de agosto de 2026";
