// Datos de la empresa que aparecen en las paginas legales.
//
// Estan aca y no repetidos en cada pagina porque Meta, y cualquier cliente que
// lea los terminos, esperan que los tres documentos digan exactamente lo mismo.
// Si estos datos viven en tres archivos, tarde o temprano dicen tres cosas.
//
// ⚠️ FALTA COMPLETAR: los campos marcados con TODO son los unicos que no pude
// saber leyendo el codigo. Sin ellos los documentos no son validos como tales.
export const EMPRESA = {
  nombreComercial: "Argencore",
  // TODO: razon social completa, como figura en AFIP.
  razonSocial: "TODO — razon social",
  // TODO: CUIT.
  cuit: "TODO — CUIT",
  // TODO: domicilio legal. Meta lo pide para la verificacion de empresa, asi
  // que conviene que coincida con el que cargues alli.
  domicilio: "TODO — domicilio legal",
  email: "argencoresolutions@gmail.com",
  // El servicio que prestamos, dicho igual en los tres documentos.
  servicio: "un asistente automatico que responde consultas por WhatsApp en nombre de empresas",
} as const;

// Fecha de ultima actualizacion de los tres documentos. Se cambia a mano cuando
// se edita alguno: es un dato legal, no la fecha del build.
export const ACTUALIZADO = "13 de agosto de 2026";
