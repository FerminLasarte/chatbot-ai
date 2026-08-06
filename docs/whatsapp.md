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

El Verify Token ya esta generado y cargado en Railway. **Falta el App Secret**:
sin el, todos los mensajes entrantes se rechazan con 401 (la firma no se puede
validar).

## Paso 3 — Registrar el webhook

En WhatsApp -> Configuracion -> Webhooks:

- **URL de devolucion de llamada**:
  `https://api-production-9187.up.railway.app/api/v1/webhooks/whatsapp`
- **Token de verificacion**: el `WHATSAPP_VERIFY_TOKEN` cargado en Railway.
- Suscribirse al campo **`messages`**. Sin esa suscripcion Meta valida la URL
  pero nunca envia nada, y el sintoma es un bot que "no responde" sin ningun
  error visible.

## Paso 4 — Datos de cada cliente (en el panel)

Por cada negocio que conectes, en `/panel/{cliente}` -> seccion WhatsApp:

| Campo | Que es |
| --- | --- |
| Phone number ID | Un numero largo que da Meta. **No es** el numero de telefono. |
| Access token | Autoriza a enviar en nombre de ese numero. |

Se guarda cifrado y la API no lo devuelve nunca: solo informa si esta cargado.

## Probar antes de tener un cliente real

Meta da un **numero de prueba** gratis y un **token temporal** (dura ~24 h) en
WhatsApp -> Configuracion de la API. Alcanza para verificar el circuito
completo, con dos limitaciones:

- El numero de prueba solo puede escribirle a numeros que registres a mano en
  esa misma pantalla (hasta 5).
- El token vence a las 24 h: sirve para probar, no para dejarlo andando.

## Para produccion de verdad

- **Verificacion de la empresa** (Meta Business Verification). Puede tardar
  dias: conviene empezarla apenas se pueda, en paralelo con todo lo demas.
- **Token permanente**: se genera con un *System User* en Business Settings, en
  vez del token temporal de prueba.
- **Ventana de 24 horas**: fuera de ella no se puede mandar texto libre, solo
  plantillas aprobadas por Meta. Para un bot que *responde* consultas no es un
  problema (siempre contesta dentro de la ventana), pero si algun dia se quiere
  escribir primero, hay que aprobar plantillas.

## Limite pendiente

El proveedor de embeddings esta en 3 requests por minuto (plan sin medio de
pago). Por WhatsApp los mensajes llegan en rafagas: si tres personas escriben
en el mismo minuto, la tercera recibe el mensaje de disculpas. Conviene
destrabarlo antes de conectar clientes reales.
