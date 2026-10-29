# Integración WhatsApp Business (Cloud API de Meta)

## Cómo funciona
1. La lógica de negocio **encola** la notificación en `notifications` dentro de su misma transacción (si se revierte, no se envía nada).
2. El `worker` (cada 30 s) toma las pendientes con `FOR UPDATE SKIP LOCKED` y las envía **como plantilla aprobada**.
3. Reintentos con retroceso exponencial (30 s, 1, 2, 4 min) solo para errores temporales (red, 5xx, 429, límites de tasa); errores permanentes (p. ej. `131026` número sin WhatsApp) pasan a `FAILED`. Máximo 5 intentos.
4. El webhook actualiza `delivery_status` (`sent/delivered/read/failed`) y registra las bajas.

| Evento | Tipo | Plantilla (por defecto) | Variables |
|---|---|---|---|
| Código de ingreso | OTP | `sgrs_codigo` (autenticación) | {{1}} código + botón copiar código |
| Pago aprobado | `PAYMENT_APPROVED` | `sgrs_pago_confirmado` | {{1}} rifa · {{2}} números · {{3}} enlace |
| Recordatorio 24 h antes | `DRAW_REMINDER` | `sgrs_recordatorio_sorteo` | {{1}} rifa · {{2}} fecha · {{3}} enlace para verificar |
| Ganador | `WINNER` | `sgrs_ganador` | {{1}} rifa · {{2}} premio · {{3}} número |
| Sorteo concluido (resto) | `DRAW_FINISHED` | `sgrs_sorteo_concluido` | {{1}} rifa · {{2}} número ganador · {{3}} enlace |

El ganador recibe solo `sgrs_ganador`; el resto, `sgrs_sorteo_concluido`.

## Plantillas a registrar en Meta (idioma `es`)
- **sgrs_codigo** — categoría *Authentication*, con botón "Copiar código"; vigencia 5 min.
- **sgrs_pago_confirmado** — *Utility*: «Hola, tu pago de la rifa {{1}} fue confirmado. Tus números: {{2}}. Detalle: {{3}}»
- **sgrs_recordatorio_sorteo** — *Utility*: «Recordatorio: la rifa {{1}} se sortea el {{2}}. Verifica el resultado aquí: {{3}}»
- **sgrs_ganador** — *Utility*: «¡Felicidades! Ganaste {{2}} en la rifa {{1}} con el número {{3}}. El administrador te contactará.»
- **sgrs_sorteo_concluido** — *Utility*: «El sorteo de {{1}} concluyó. Número ganador: {{2}}. Verifica el resultado: {{3}}»

Meta decide la categoría final y puede reclasificar una plantilla como *Marketing* (con otra tarifa). Los nombres se pueden cambiar con `WA_TPL_*`.

## Puesta en marcha
1. Crear una app en Meta for Developers, añadir el producto **WhatsApp** y un número de negocio verificado (Business Manager).
2. Generar un **token permanente** (usuario del sistema) y anotar el `Phone number ID`.
3. Registrar y esperar la aprobación de las plantillas.
4. Variables de entorno (ver `.env.example`): `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `SGRS_PUBLIC_URL`, `SGRS_ENV=production`.
5. Webhook: URL `https://TU-DOMINIO/api/v1/webhooks/whatsapp`, token de verificación = `WHATSAPP_VERIFY_TOKEN`, suscribir el campo `messages`. Las peticiones se aceptan solo con firma `X-Hub-Signature-256` válida (HMAC con `WHATSAPP_APP_SECRET`).

Sin `WHATSAPP_TOKEN`: en desarrollo el OTP se registra en memoria y las notificaciones permanecen en cola; con `SGRS_ENV=production` el OTP **falla** (`502 OTP_SEND_FAILED`) en lugar de omitirse en silencio.

## Consentimiento y bajas
- Solo se escribe al número que el propio usuario verificó con OTP; las notificaciones son transaccionales.
- Si el usuario responde `BAJA`, `STOP`, `PARAR` o `CANCELAR`, se marca `users.notify_optout` y sus notificaciones pasan a `SKIPPED`. El OTP no se bloquea por baja (es una acción iniciada por el usuario).
- Revisa la política de uso de WhatsApp Business y la normativa de datos personales aplicable (en Colombia, Ley 1581 de 2012) antes de publicar.

## Estado de la verificación
Probado contra un servidor simulado (formato del payload, reintentos, errores, firma y estados del webhook). **No** se ha probado contra la API real de Meta: no había credenciales ni acceso de red a `graph.facebook.com` en el entorno de desarrollo. Antes de producción, envía un mensaje de prueba real con cada plantilla y confirma que la estructura de componentes coincide con la documentación vigente de Meta.
