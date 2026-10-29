# Despliegue en Vercel (beta cerrada)

Arquitectura: una función Python (FastAPI, `index.py`) + archivos estáticos de `public/` en la CDN + PostgreSQL de Neon.
No hay worker: el mantenimiento (expirar reservas, cerrar rifas, recordatorios) corre de forma perezosa en las peticiones
(`SGRS_LAZY_MAINTENANCE=1`, máx. cada 20 s por instancia) y con un Cron diario de respaldo (`/api/v1/cron/tick`).

## Variables de entorno
| Variable | Valor |
|---|---|
| `DATABASE_URL` | La inyecta la integración de Neon (el esquema se crea solo con `SGRS_AUTO_SCHEMA=1`). Con prefijo personalizado (p. ej. `STORAGE_URL`) la app también la encuentra: rastrea cualquier variable con una URL `postgres://`, prefiriendo la del pooler |
| `SGRS_ENV` | `production` |
| `SGRS_AUTO_SCHEMA` | `1` |
| `SGRS_STORAGE` | `db` (comprobantes en PostgreSQL; límite 4 MB por archivo) |
| `SGRS_LAZY_MAINTENANCE` | `1` |
| `SGRS_BETA_KEY` | Clave de invitación que se entrega a los testers |
| `SGRS_DEV_ECHO_OTP` | `1` solo en beta: el código OTP se muestra en pantalla. **Quitar al conectar WhatsApp/SMS** |
| `CRON_SECRET` | Secreto del Cron (Vercel lo envía como `Authorization: Bearer`) |
| `SGRS_JWT_SECRET` | Opcional; si falta, se deriva de `DATABASE_URL` |
| `SGRS_PUBLIC_URL` | URL pública (para los enlaces de las notificaciones) |

## Variables adicionales (opcionales)
| Variable | Efecto |
|---|---|
| `SGRS_OTP_IP_LIMIT` | Códigos OTP por hora y por IP (def. 20). Súbela si varios testers comparten red |
| `SGRS_MAX_RAFFLES_PER_DAY` | Rifas que un usuario puede crear por día (def. 10) |
| `SGRS_POOL_MAX` | Conexiones por instancia a la base (def. 5; el pool se activa solo en producción) |
| `SGRS_REQUIRE_TERMS` | `1` exige aceptar términos y privacidad (activo por defecto en producción) |
| `SENTRY_DSN` | Activa la captura de errores (sin datos personales ni cuerpos de petición) |
| `SGRS_LOG_LEVEL` | `INFO` por defecto; los registros son una línea JSON por petición, sin datos personales |

## Operación
- **Monitor externo:** apunta UptimeRobot/Better Stack a `https://TU-URL/api/v1/health` (200 = base de datos responde; 503 = degradado).
- **Migraciones:** con `SGRS_AUTO_SCHEMA=1` se aplican solas al primer arranque tras cada despliegue. Todo cambio de esquema es un archivo nuevo `migrations/NNNN_nombre.sql`; nunca se edita uno ya publicado. Manual: `python -m app.migrate`.
- **Cron diario** (`/api/v1/cron/tick`): mantenimiento y verificación de la cadena de auditoría (`auditoria_ok`). Si fuera `false`, el servidor registra un error.
- **Avisos de WhatsApp:** se envían al aprobar un pago y al sortear (no esperan al cron); los pendientes se reenvían desde el panel del organizador.
- **Referencia de error:** una respuesta 500 trae `request_id`; es el mismo valor que aparece en los registros (`rid`).

## Limitaciones de la beta
- Cualquier persona con la clave puede iniciar sesión con **cualquier** número (el código no viaja por mensajería): úsese solo con pagos ficticios.
- Los proyectos Vercel con Hobby limitan los Cron a una ejecución diaria.
- Para salir de la beta: configurar WhatsApp o SMS (`docs/WHATSAPP.md`), quitar `SGRS_DEV_ECHO_OTP` y `SGRS_BETA_KEY`.

## Diagnóstico
- `503 DB_NOT_CONFIGURED` (en producción): ninguna variable de entorno contiene una URL postgres. Conecta Neon al proyecto en el entorno *Production* y **redespliega**.
- Las variables nuevas solo se aplican a despliegues nuevos.
