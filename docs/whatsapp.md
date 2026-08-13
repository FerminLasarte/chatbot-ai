# Conectar WhatsApp

El codigo esta listo y desplegado. Lo que queda son pasos en la cuenta de Meta,
que no se pueden automatizar: requieren tu identidad y, para produccion, la
verificacion de tu empresa.

## Lo que ya esta verificado

El webhook de produccion responde bien al handshake de Meta:

```
GET  /api/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=...&hub.challenge=X
  -> 200 con el challenge si el token coincide, 403 si no
POST /api/v1/webhooks/whatsapp sin firma valida
  -> 401
```

## Paso 1 — Crear la App

1. Entra a <https://developers.facebook.com/apps> y crea una App de tipo
   **Business** (Negocios).
2. En el panel de la App, agrega el producto **WhatsApp**.

## Paso 2 — Datos que van al servidor (una sola vez)

Son de la App, no de un cliente: valen para todos los numeros que cuelguen de
ella.

| Dato | Donde sale | Variable |
| --- | --- | --- |
| App Secret | Configuracion de la App -> Basica -> "Clave secreta" | `WHATSAPP_APP_SECRET` |
| Verify Token | Lo inventas vos | `WHATSAPP_VERIFY_TOKEN` |
| App ID | Arriba de todo en el panel de la App | `WHATSAPP_APP_ID` |
| Config ID | WhatsApp -> Configuracion -> Embedded Signup | `WHATSAPP_CONFIG_ID` |
| URL del panel | La tuya | `ONBOARDING_BASE_URL` |

El Verify Token ya esta generado y cargado en Railway. **Falta el App Secret**:
sin el, todos los mensajes entrantes se rechazan con 401 (la firma no se puede
validar).

El App ID y el Config ID son **publicos**: viajan al navegador del cliente
porque los necesita el SDK de Facebook. El App Secret nunca sale del servidor.

`ONBOARDING_BASE_URL` tiene que ser **https** en produccion o la API no
arranca: el link de onboarding lleva un token en la URL y sobre http viajaria
en claro.

## Paso 3 — Registrar el webhook

En WhatsApp -> Configuracion -> Webhooks:

- **URL de devolucion de llamada**:
  `https://api-production-9187.up.railway.app/api/v1/webhooks/whatsapp`
- **Token de verificacion**: el `WHATSAPP_VERIFY_TOKEN` cargado en Railway.
- Suscribirse al campo **`messages`**. Sin esa suscripcion Meta valida la URL
  pero nunca envia nada, y el sintoma es un bot que "no responde" sin ningun
  error visible.

## Paso 4 — Generar el Config ID del alta

En **WhatsApp -> Configuracion -> Embedded Signup**, crea una configuracion.
Ahi se define que permisos pide el popup y que pasos ve el cliente. Meta te
devuelve un `config_id`: eso va en `WHATSAPP_CONFIG_ID`.

No es codigo, es un dato de configuracion. Sin el, la pagina de onboarding
responde 503 a proposito, para que el error lo veas vos y no el cliente frente
a un popup de Facebook que muere sin explicacion.

## Paso 5 — Dar de alta un cliente

El cliente **no toca nada de Meta**. El flujo es:

1. En `/panel/{cliente}` -> seccion WhatsApp -> **Generar link para el
   cliente**.
2. Le mandas ese link por mail o WhatsApp. Vence en 72 horas
   (`ONBOARDING_LINK_TTL_HOURS`); si se pasa, generas otro.
3. El cliente abre el link, toca "Conectar WhatsApp", entra con su cuenta de
   Facebook y elige o crea su numero.
4. Al terminar, el servidor canjea el codigo por un token permanente, engancha
   el webhook a la cuenta del cliente y registra el numero. Queda listo.

Lo que hace el link, y lo que no: solo permite ver el nombre del cliente y
conectarle un WhatsApp si todavia no tiene. No da acceso a conversaciones, ni
documentos, ni consumo, y **no pisa un WhatsApp ya conectado**. Para cambiar un
numero hay que desconectarlo primero desde el panel.

Si algo falla contra Meta, no se guarda nada a medias: el cliente sigue
figurando como desconectado y puede reintentar con el mismo link. La unica
excepcion es el registro del numero, que si falla deja el alta hecha con una
advertencia (pasa cuando el numero ya tenia verificacion en dos pasos con otro
PIN).

### Carga a mano (plan B)

En la misma seccion, plegado bajo "Cargar las credenciales a mano", siguen los
campos de siempre:

| Campo | Que es |
| --- | --- |
| Phone number ID | Un numero largo que da Meta. **No es** el numero de telefono. |
| Access token | Autoriza a enviar en nombre de ese numero. |

Se guarda cifrado y la API no lo devuelve nunca: solo informa si esta cargado.
Sirve para los casos que el alta automatica no cubre, por ejemplo un numero ya
dado de alta en otra App de Meta.

## Probar antes de tener un cliente real

Meta da un **numero de prueba** gratis y un **token temporal** (dura ~24 h) en
WhatsApp -> Configuracion de la API. Alcanza para verificar el circuito
completo, con dos limitaciones:

- El numero de prueba solo puede escribirle a numeros que registres a mano en
  esa misma pantalla (hasta 5).
- El token vence a las 24 h: sirve para probar, no para dejarlo andando.

## Acompanar al cliente

El cliente **no tiene donde entrar por su cuenta**: no hay registro ni portal.
La unica puerta es el link que vos le generas y le mandas. Si no se lo mandas,
no ve nada.

### Lo que conviene decirle antes de mandarselo

- Que tenga a mano el **telefono** donde va a recibir el codigo de Meta.
- Que use un numero que **no este activo en la app comun de WhatsApp**. Si el
  numero ya tiene WhatsApp normal o WhatsApp Business, primero hay que borrar
  esa cuenta desde la app (Ajustes -> Cuenta -> Eliminar mi cuenta) o usar otro
  numero. Es el motivo por el que mas se traba el alta.
- Que necesita una **cuenta de Facebook**. No hace falta que tenga Business
  Manager armado: el asistente se lo crea en el momento.
- Que son 2-3 minutos y no cierre la ventana hasta el final.

### Problemas comunes

| Lo que dice el cliente | Que pasa | Que hacer |
| --- | --- | --- |
| "No me abre la ventana" | Bloqueador de ventanas emergentes o de publicidad | Que permita popups en el sitio y recargue. La pagina avisa sola si el bloqueador impidio cargar el conector. |
| "Me dice que el numero ya esta en uso" | El numero tiene WhatsApp activo | Borrar la cuenta desde la app de WhatsApp, o usar otro numero. |
| "Cerre la ventana sin querer" | El alta no se completo | Que vuelva a abrir el mismo link. No quedo nada a medias. |
| "El link no anda / vencio" | Pasaron mas de 72 h | Genera otro desde el panel. |
| "Ya esta conectado" | El alta ya se hizo | No hay nada que hacer. Verificalo en el panel. |
| "Dice que quedo conectado pero con una advertencia" | Meta no acepto registrar el numero, casi siempre por verificacion en dos pasos previa | Lo resolves vos desde Meta: hay que desactivar el PIN viejo del numero. El resto del alta quedo bien. |

### Como verificar que quedo bien

En `/panel/{cliente}` -> WhatsApp tiene que decir **"Conectado — el bot responde
por WhatsApp"**. La prueba de fuego es mandarle un mensaje al numero del cliente
y ver que conteste.

## Tramites de Meta: el cuello de botella real

El alta automatica funciona en modo desarrollo con cuentas agregadas como
**tester** de la App. Para que la use un cliente real hacen falta tres tramites
de Meta que no dependen del codigo y que son **lo que mas tiempo va a consumir**.

Conviene arrancarlos EN PARALELO con el desarrollo, no despues.

| Tramite | Donde | Cuanto tarda |
| --- | --- | --- |
| Verificacion de la empresa | Business Manager -> Configuracion empresarial -> Seguridad -> Verificacion | Dias |
| Acceso avanzado (App Review) | Panel de la App -> Revision de la app | Dias a un par de semanas |
| Publicar la App | Panel de la App | Inmediato, una vez cumplido lo anterior |

**Verificacion de la empresa** es sobre *tu* empresa, no la del cliente.

**Acceso avanzado** hay que pedirlo para los permisos
`whatsapp_business_management` y `whatsapp_business_messaging`. Meta pide:

- Un screencast del flujo de Embedded Signup funcionando de punta a punta. Se
  puede grabar con una cuenta de prueba agregada como tester, antes de tener
  cliente real.
- URL de politica de privacidad y de terminos de servicio.
- Descripcion del caso de uso (bot de atencion al cliente por WhatsApp para
  PyMEs).

**Publicar la App** ademas exige icono, categoria y el Data Use Checkup
completo.

### Orden recomendado

1. Arrancar la verificacion de empresa (es lo mas lento y no depende de nada).
2. En paralelo, probar el alta con una cuenta agregada como tester. Esto ya
   funciona sin esperar ninguna aprobacion.
3. Grabar el screencast y pedir el Acceso avanzado.
4. Publicar la App cuando Meta apruebe.
5. Recien ahi un cliente real puede pasar por el flujo sin ser tester.

## Para produccion de verdad

- **Verificacion de la empresa** (Meta Business Verification). Puede tardar
  dias: conviene empezarla apenas se pueda, en paralelo con todo lo demas.
- **Token permanente**: se genera con un *System User* en Business Settings, en
  vez del token temporal de prueba.
- **Ventana de 24 horas**: fuera de ella no se puede mandar texto libre, solo
  plantillas aprobadas por Meta. Para un bot que *responde* consultas no es un
  problema (siempre contesta dentro de la ventana), pero si algun dia se quiere
  escribir primero, hay que aprobar plantillas.

## Limite de embeddings (resuelto)

El proveedor de embeddings estuvo un tiempo en 3 requests por minuto (plan sin
medio de pago), lo que con trafico real de WhatsApp se notaba enseguida: si tres
personas escribian en el mismo minuto, la tercera recibia el mensaje de
disculpas. Ya esta destrabado.
