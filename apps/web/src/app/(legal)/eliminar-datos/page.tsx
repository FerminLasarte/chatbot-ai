import { EMPRESA } from "@/lib/empresa";

export const metadata = {
  title: "Eliminacion de datos — Argencore",
  description: "Como pedir que se eliminen tus datos del asistente de WhatsApp de Argencore.",
};

// Esta es la URL que va en Meta -> Configuracion basica -> "Eliminacion de datos
// de usuario", con la opcion "URL de instrucciones". Meta la revisa: tiene que
// explicar el procedimiento concreto, no remitir a una politica generica.

export default function EliminarDatos() {
  return (
    <>
      <h1>Como eliminar tus datos</h1>
      <p className="text-texto-suave">
        Instrucciones para pedir la eliminacion de los datos tratados por el asistente de WhatsApp
        de {EMPRESA.nombreComercial}.
      </p>

      <h2>Si le escribiste por WhatsApp a una empresa</h2>
      <p>
        Los datos que guardamos de vos son tu numero de telefono y el contenido de la conversacion
        que tuviste con el asistente.
      </p>
      <p>Para pedir que se eliminen, tenes dos caminos:</p>
      <ul>
        <li>
          <strong>Pedirselo a la empresa</strong> a la que le escribiste. Es la responsable de esos
          datos y nos traslada el pedido.
        </li>
        <li>
          <strong>Escribirnos a nosotros</strong> a{" "}
          <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a> con el asunto{" "}
          <strong>&ldquo;Eliminacion de datos&rdquo;</strong>, indicando:
          <ul>
            <li>el numero de telefono desde el que escribiste, y</li>
            <li>el nombre de la empresa con la que hablaste.</li>
          </ul>
        </li>
      </ul>
      <p>
        Necesitamos esos dos datos porque son los unicos que permiten encontrar tu conversacion:
        buscamos por numero dentro de la empresa que indiques.
      </p>

      <h2>Si sos una empresa cliente</h2>
      <p>
        Escribinos a <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a> desde el correo de
        contacto de tu cuenta y pedinos la eliminacion. Podemos borrar los documentos que cargaste,
        el historial de conversaciones, o la cuenta entera.
      </p>
      <p>
        Si borras la cuenta, se eliminan tambien todas sus conversaciones, mensajes y documentos.
      </p>
      <p>
        Aparte, conviene que revoques la autorizacion de la app desde tu cuenta de Meta Business
        (Configuracion empresarial &rarr; Aplicaciones), que es lo que corta nuestro acceso a tu
        numero de WhatsApp de inmediato.
      </p>

      <h2>Plazos</h2>
      <p>
        Confirmamos la recepcion del pedido dentro de los <strong>5 dias habiles</strong> y lo
        completamos dentro de los <strong>30 dias corridos</strong>.
      </p>

      <h2>Que puede quedar despues</h2>
      <p>Con honestidad, no todo desaparece en el mismo instante:</p>
      <ul>
        <li>
          Las copias de seguridad se sobrescriben en sus ciclos habituales, asi que los datos pueden
          sobrevivir ahi unos dias mas antes de desaparecer.
        </li>
        <li>
          Los mensajes tal como los ves en tu propio telefono, y los que quedan en la bandeja de
          WhatsApp de la empresa, los controla Meta y no nosotros. Para esos hay que usar WhatsApp
          directamente.
        </li>
        <li>
          Podemos conservar registros minimos si una obligacion legal nos lo exige, y solo por el
          plazo que esa obligacion imponga.
        </li>
      </ul>

      <h2>Contacto</h2>
      <p>
        <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a>
      </p>
    </>
  );
}
