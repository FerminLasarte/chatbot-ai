import { EMPRESA } from "@/lib/empresa";

export const metadata = {
  title: "Terminos del servicio — Argencore",
  description: "Condiciones de uso del asistente de WhatsApp de Argencore.",
};

export default function Terminos() {
  return (
    <>
      <h1>Terminos del servicio</h1>
      <p className="text-texto-suave">
        Condiciones bajo las que {EMPRESA.nombreComercial} presta el servicio de asistente por
        WhatsApp.
      </p>

      <h2>1. Quien presta el servicio</h2>
      <p>
        {EMPRESA.razonSocial} (CUIT {EMPRESA.cuit}), con domicilio en {EMPRESA.domicilio}, en
        adelante &ldquo;{EMPRESA.nombreComercial}&rdquo;.
      </p>

      <h2>2. A quien le aplican estos terminos</h2>
      <p>
        A la <strong>empresa que contrata el servicio</strong> (&ldquo;el Cliente&rdquo;), no a los
        consumidores que le escriben. La relacion con esos consumidores es del Cliente: nosotros no
        tenemos vinculo contractual con ellos.
      </p>

      <h2>3. Que incluye el servicio</h2>
      <p>
        Un asistente automatico que responde consultas por WhatsApp en nombre del Cliente, usando la
        informacion que el propio Cliente carga (documentos, precios, preguntas frecuentes) y las
        instrucciones de comportamiento que define. Incluye un panel de administracion desde el que
        se configura el asistente, se consultan las conversaciones y se pausa cuando alguien quiere
        atender a mano.
      </p>
      <p>
        Hoy ese panel lo opera {EMPRESA.nombreComercial}: el Cliente pide los cambios y nosotros los
        aplicamos. Si se le otorga acceso directo, aplican tambien las obligaciones del punto 5.
      </p>

      <h2>4. Cuenta de WhatsApp del Cliente</h2>
      <p>
        Para operar necesitamos autorizacion sobre el numero de WhatsApp Business del Cliente. El
        Cliente la otorga por el flujo de conexion de Meta, y puede revocarla cuando quiera desde su
        cuenta de Meta Business. Esa autorizacion la usamos solo para enviar y recibir mensajes en
        su nombre, nunca para otra cosa.
      </p>
      <p>
        El Cliente declara que el numero que conecta es suyo o que esta autorizado a usarlo, y que
        cumple las{" "}
        <a
          href="https://www.whatsapp.com/legal/business-policy/"
          target="_blank"
          rel="noopener noreferrer"
        >
          politicas de WhatsApp Business
        </a>
        . Meta puede suspender un numero por incumplirlas, y eso escapa a nuestro control.
      </p>

      <h2>5. Obligaciones del Cliente</h2>
      <ul>
        <li>
          Tener derecho sobre el contenido que carga, y que ese contenido no sea ilegal ni de
          terceros sin permiso.
        </li>
        <li>
          Cumplir la normativa de proteccion de datos frente a sus propios usuarios, incluida la de
          informarles como se tratan sus datos.
        </li>
        <li>No usar el servicio para spam, engano, ni contenido prohibido por Meta o por la ley.</li>
        <li>
          Si se le otorgo acceso al panel, cuidar esas credenciales y avisarnos ante cualquier
          sospecha de uso indebido.
        </li>
      </ul>

      <h2>6. Limites de uso</h2>
      <p>
        Cada plan tiene un tope mensual de mensajes. Al alcanzarlo, el asistente deja de responder
        hasta el periodo siguiente o hasta que se amplie el tope. El Cliente puede consultar su
        consumo cuando quiera.
      </p>

      <h2>7. Que no garantizamos</h2>
      <p>
        El asistente genera respuestas con un modelo de lenguaje. Aunque se apoya en la informacion
        que carga el Cliente, <strong>puede equivocarse o dar respuestas incompletas</strong>. El
        Cliente es responsable de revisar la informacion que publica y de supervisar el canal; para
        eso se pueden consultar las conversaciones y pausar el asistente en cualquier momento.
      </p>
      <p>
        No garantizamos disponibilidad ininterrumpida: el servicio depende de terceros (Meta,
        proveedores de modelos, el hosting) que pueden fallar o cambiar sus condiciones.
      </p>
      <p>
        El servicio no reemplaza asesoramiento profesional. No debe usarse como unico canal para
        urgencias ni para decisiones medicas, legales o financieras.
      </p>

      <h2>8. Responsabilidad</h2>
      <p>
        En la medida que lo permita la ley, nuestra responsabilidad se limita al monto abonado por
        el Cliente en los ultimos tres meses. No respondemos por lucro cesante ni por danos
        indirectos. Nada de esto limita la responsabilidad por dolo o culpa grave.
      </p>

      <h2>9. Precio y pago</h2>
      <p>
        Los precios, la modalidad y la periodicidad se acuerdan por separado con cada Cliente. La
        falta de pago habilita a suspender el servicio previo aviso.
      </p>

      <h2>10. Baja</h2>
      <p>
        Cualquiera de las partes puede dar de baja el servicio avisando con 30 dias. Al darse de
        baja, el Cliente puede pedir una copia de sus datos y su eliminacion (ver{" "}
        <a href="/eliminar-datos">eliminacion de datos</a>). Revocar la autorizacion de WhatsApp
        desde Meta corta el servicio de inmediato.
      </p>

      <h2>11. Cambios</h2>
      <p>
        Podemos actualizar estos terminos. Los cambios de fondo se avisan por correo con
        anticipacion razonable; seguir usando el servicio implica aceptarlos.
      </p>

      <h2>12. Ley aplicable</h2>
      <p>
        Estos terminos se rigen por las leyes de la Republica Argentina. Cualquier controversia se
        somete a los tribunales ordinarios competentes del domicilio de {EMPRESA.nombreComercial},
        salvo norma imperativa en contrario.
      </p>

      <h2>Contacto</h2>
      <p>
        <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a>
      </p>
    </>
  );
}
