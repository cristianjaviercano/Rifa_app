# Plan de mejoras (ejecutado el 29 oct 2026)

Origen: `DIAGNOSTICO.md`. Cada punto trae qué se hizo y cómo se verificó.

| # | Mejora | Qué se hizo | Verificación |
|---|---|---|---|
| P0.2 | Migraciones | `migrations/NNNN_*.sql` + `app/migrate.py`: transacción única, bloqueo consultivo, tabla `schema_migrations`. Una base creada antes de existir el sistema (tu Neon) se reconoce como línea base y solo recibe las nuevas | 4 pruebas: base nueva, base heredada, migración defectuosa revierte todo, numeración sin huecos |
| P0.3 | Avisos sin esperar al cron | Envío inmediato tras aprobar (3) y sortear (10); si WhatsApp falla, queda en cola. Endpoint y botón «Enviar pendientes» en el panel; resumen de enviados/pendientes/fallidos | 3 pruebas nuevas con WhatsApp simulado |
| P0.4 | Textos legales | Páginas `#/terminos` y `#/privacidad` (**borrador**, con huecos por completar) y casilla obligatoria al ingresar; se registra fecha y versión aceptadas (también en la auditoría). Cambiar `TERMS_VERSION` pide aceptar de nuevo | 2 pruebas + E2E |
| P1.5 | Grilla ligera | `GET /raffles/{id}/board`: 1 carácter por boleta (20 000 boletas ≈ 20 KB en vez de 2,2 MB), `ETag`/304, reservas por número de boleta, sondeo pausado en segundo plano, pintado por tandas, «Elegir al azar» | 2 pruebas + E2E |
| P1.6 | Conexiones | Pool por instancia (`psycopg_pool`) compatible con el pooler de Neon; activo en producción | prueba con 12 hilos y 40 peticiones |
| P1.7 | Abuso | Límites en PostgreSQL: códigos por IP (20/h) y por número (5/h), verificaciones por IP (30/h), 10 claves de beta erróneas por IP cada 15 min (bloquea también la correcta), 60 subidas/h por usuario, 10 rifas/día por usuario | 6 pruebas |
| P1.9 | Observabilidad | `/api/v1/health` para monitores, una línea JSON por petición sin datos personales, referencia de error (`request_id`), Sentry opcional sin cuerpos de petición | 7 pruebas |
| P2.12 | Auditoría | El cron verifica la cadena (últimos 5 000) y registra un error si se rompe | prueba que altera un registro y lo detecta |
| P2.13 | Pruebas | Worker cubierto; 101 pruebas; E2E en modo producción (migraciones, pool, consentimiento, límites activos) | E2E OK, 0 respuestas 5xx |
| P2.14 | Limpieza | Imports, `raise … from None`, imports al inicio | `ruff` sin avisos de esas reglas |

## Pendiente
- **P0.1** Definir `SGRS_BETA_KEY` en Vercel (acción tuya) y redesplegar.
- **P1.8** Refresh token y cierre de sesión en servidor.
- **P1.10** Verificar la ventana de restauración de Neon y plan de almacenamiento de objetos para comprobantes.
- **P2.11** Cadena de auditoría por rifa (hoy el bloqueo global cuesta ≈ 3–10 %).
- **P2.15** Experiencia: formulario de creación por pasos y vista previa del comprador.
- **P2.16** Validar Docker Compose y el job E2E del CI en un entorno con Docker.
- **Textos legales**: revisión por un abogado y completar los datos entre corchetes.
- **Derecho de supresión**: hoy se atiende por correo; falta una opción «eliminar mi cuenta» en la app.
