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

## Limitaciones de la beta
- Cualquier persona con la clave puede iniciar sesión con **cualquier** número (el código no viaja por mensajería): úsese solo con pagos ficticios.
- Los proyectos Vercel con Hobby limitan los Cron a una ejecución diaria.
- Para salir de la beta: configurar WhatsApp o SMS (`docs/WHATSAPP.md`), quitar `SGRS_DEV_ECHO_OTP` y `SGRS_BETA_KEY`.

## Diagnóstico
- `503 DB_NOT_CONFIGURED` (en producción): ninguna variable de entorno contiene una URL postgres. Conecta Neon al proyecto en el entorno *Production* y **redespliega**.
- Las variables nuevas solo se aplican a despliegues nuevos.
