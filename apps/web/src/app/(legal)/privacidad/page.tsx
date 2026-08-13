import { EMPRESA } from "@/lib/empresa";

export const metadata = {
  title: "Politica de privacidad — Argencore",
  description: "Que datos trata el asistente de WhatsApp de Argencore, para que, y con quien.",
};

export default function Privacidad() {
  return (
    <>
      <h1>Politica de privacidad</h1>
      <p className="text-zinc-500">
        Como tratamos los datos personales en el asistente de WhatsApp de {EMPRESA.nombreComercial}.
      </p>

      <h2>Quienes somos y que hacemos</h2>
      <p>
        {EMPRESA.razonSocial} (CUIT {EMPRESA.cuit}), con domicilio en {EMPRESA.domicilio}, opera{" "}
        {EMPRESA.servicio}.
      </p>
      <p>
        Hay que distinguir dos roles, porque de eso depende a quien reclamarle. La{" "}
        <strong>empresa que contrata el servicio</strong> es la responsable de los datos: define que
        responde el asistente y por que se comunica con vos. {EMPRESA.nombreComercial} actua como{" "}
        <strong>encargado del tratamiento</strong>: procesamos esos datos siguiendo sus
        instrucciones y no los usamos para fines propios.
      </p>
      <p>
        En la practica: si le escribiste por WhatsApp a un negocio y te contesto este asistente, la
        relacion es con ese negocio. Nosotros ponemos la tecnologia.
      </p>

      <h2>Que datos tratamos</h2>
      <p>Cuando le escribis por WhatsApp a una empresa que usa nuestro asistente, tratamos:</p>
      <ul>
        <li>
          <strong>Tu numero de telefono</strong>, que es lo que permite reconocer que los mensajes
          de una conversacion son tuyos y contestarte.
        </li>
        <li>
          <strong>El contenido de tus mensajes</strong> y las respuestas del asistente, con su fecha
          y hora.
        </li>
      </ul>
      <p>
        No pedimos ni necesitamos datos sensibles. Te recomendamos no enviar por este canal
        informacion que no le darias a la empresa por telefono: numeros de tarjeta, claves, ni datos
        de salud.
      </p>
      <p>
        Aparte de eso, la empresa cliente carga sus propios documentos (catalogos, precios,
        preguntas frecuentes) para que el asistente sepa que contestar. Ese material es de la
        empresa y normalmente no contiene datos personales de terceros.
      </p>

      <h2>Para que los usamos</h2>
      <p>
        Unicamente para que el asistente pueda entender tu consulta y responderla en nombre de la
        empresa, y para que la empresa pueda retomar la conversacion a mano si hace falta.
      </p>
      <p>
        <strong>No vendemos datos</strong>, no armamos perfiles publicitarios y no usamos tus
        mensajes para entrenar modelos de inteligencia artificial.
      </p>

      <h2>Con quien los compartimos</h2>
      <p>
        Para que el asistente funcione, tus mensajes pasan por estos proveedores, cada uno con su
        propia politica de privacidad:
      </p>
      <ul>
        <li>
          <strong>Meta Platforms</strong> — es quien opera WhatsApp y por donde llega y sale cada
          mensaje.
        </li>
        <li>
          <strong>Anthropic</strong> — el modelo de lenguaje que redacta la respuesta. Recibe tu
          mensaje, los ultimos mensajes de la conversacion y los fragmentos de los documentos de la
          empresa que sirvan para contestarte.
        </li>
        <li>
          <strong>Voyage AI</strong> — convierte textos en representaciones numericas para poder
          buscar en los documentos de la empresa. Recibe el texto de tu consulta.
        </li>
        <li>
          <strong>Railway</strong> — donde corren el servidor y la base de datos.
        </li>
        <li>
          <strong>Sentry</strong> — nos avisa cuando algo falla. Est&aacute; configurado para{" "}
          <strong>no</strong> recibir el contenido de las conversaciones: le llega el detalle
          t&eacute;cnico del error y de qu&eacute; empresa se trata, no lo que escribiste. Un
          mensaje de error puede igualmente arrastrar alg&uacute;n dato t&eacute;cnico, por eso lo
          nombramos ac&aacute;.
        </li>
      </ul>
      <p>
        Estos proveedores estan fuera de Argentina, asi que tus datos se procesan en el exterior.
        Fuera de ellos y de la empresa cliente, no compartimos nada con nadie, salvo que nos lo
        exija una autoridad competente.
      </p>

      <h2>Cuanto tiempo los guardamos</h2>
      <p>
        Las conversaciones se conservan mientras la empresa siga usando el servicio, porque son su
        historial de atencion. <strong>No hay borrado automatico por antiguedad.</strong> Se
        eliminan cuando la empresa cierra su cuenta, o antes si vos o la empresa lo piden: ver{" "}
        <a href="/eliminar-datos">como eliminar tus datos</a>.
      </p>

      <h2>Como los protegemos</h2>
      <ul>
        <li>Todo viaja cifrado (HTTPS) entre tu telefono, WhatsApp y nuestros servidores.</li>
        <li>
          Cada empresa esta aislada de las demas: una consulta solo puede alcanzar los datos de la
          empresa a la que le escribiste.
        </li>
        <li>
          Las credenciales de WhatsApp de cada empresa se guardan cifradas, de modo que una copia de
          la base de datos por si sola no permite escribir en su nombre.
        </li>
        <li>El acceso al panel de administracion esta restringido y protegido con contrasena.</li>
      </ul>
      <p>
        Ninguna medida es infalible. Si detectamos un incidente que afecte tus datos, se lo
        notificamos a la empresa cliente y a la autoridad que corresponda.
      </p>

      <h2>Tus derechos</h2>
      <p>
        Podes pedir acceder a tus datos, corregirlos, actualizarlos o eliminarlos. Lo mas directo es
        pedirselo a la empresa a la que le escribiste, que es la responsable. Si preferis,
        escribinos a{" "}
        <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a> y lo derivamos.
      </p>
      <p>
        En Argentina, la Agencia de Acceso a la Informacion Publica es el organo de control de la
        Ley 25.326 y atiende denuncias por incumplimiento.
      </p>

      <h2>Cambios</h2>
      <p>
        Si cambiamos esta politica, actualizamos la fecha del pie. Si el cambio es de fondo, se lo
        avisamos a las empresas clientes para que puedan informar a sus usuarios.
      </p>

      <h2>Contacto</h2>
      <p>
        Por cualquier duda sobre esta politica: <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a>.
      </p>
    </>
  );
}
