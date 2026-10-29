# Rifa App

Plataforma web móvil (PWA) para **organizar campañas de recaudo y rifas con control transaccional y auditable**: reservas con vencimiento, comprobantes de pago, aprobación del organizador, arqueo contable con huella verificable, sorteo con generador criptográfico, avisos por WhatsApp y enlaces para compartir.

> **Estado:** beta cerrada con pagos ficticios. La plataforma actúa como libro de control: **no procesa ni custodia dinero**; el aportante paga directo al organizador, que valida cada pago.
> **Dirección del producto:** evolucionar hacia **crowdfunding (donación y recompensas)**, dejando las rifas como módulo opcional, porque en Colombia la rifa es un juego de suerte y azar con autorización previa. Ver [`docs/CROWDFUNDING.md`](docs/CROWDFUNDING.md).

## Qué hace
| Para quien organiza | Para quien participa |
|---|---|
| Crea la rifa con portada, galería, descripción, premios y cuentas de pago | Entra por enlace o código corto y ve el estado de los números en tiempo casi real |
| Cola de verificación con visor de comprobante; aprobar o rechazar con motivo | Elige números (o «al azar») y reporta el pago con número de transacción y/o comprobante |
| Cierre automático de ventas y **arqueo contable** con huella (hash) | Sigue su compra: en verificación, pagada, rechazada o vencida |
| Sorteo interno (generador criptográfico) o con **lotería oficial** y fuente pública | Recibe avisos por WhatsApp (pago confirmado, recordatorio, resultado) |
| Sala por organizador (portafolio), enlaces para compartir con vista previa | Consulta el resultado público y verifica la fuente |

Seguridad y confianza: inicio de sesión por código (OTP), consentimiento de términos registrado, comprobantes con acceso restringido, auditoría con cadena de hashes inmodificable, límites contra abuso y cabeceras de seguridad estrictas.

## Arquitectura
```
Navegador (PWA, JS puro) ──► FastAPI (Python 3.12) ──► PostgreSQL 16 (Neon)
                                │
                                ├─ Comprobantes e imágenes: en la base (bytea) o disco
                                ├─ WhatsApp Business (Cloud API): plantillas, cola con reintentos, webhook
                                └─ Mantenimiento: perezoso en peticiones + cron diario (o worker)
```
- **Frontend:** `public/`, JavaScript con módulos ES, sin build ni dependencias; service worker, manifest instalable, modo oscuro.
- **Backend:** `app/`, FastAPI + psycopg 3 (pool opcional); migraciones SQL versionadas en `migrations/`.
- **Concurrencia:** reserva atómica con `UPDATE … WHERE status='DISPONIBLE'`; idempotencia por clave; bloqueos con `SKIP LOCKED`.
- **Despliegue:** Vercel (función Python + CDN) y Neon; también `Dockerfile` y `docker-compose.yml`.

Más detalle: [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) y el flujo BPMN en [`docs/sgrs-flujo.bpmn`](docs/sgrs-flujo.bpmn).

## Inicio rápido (local)
Requisitos: Python 3.12+, PostgreSQL 16 y Node 20+ (solo para la prueba E2E).

```bash
pip install -r requirements.txt
export SGRS_DSN=postgresql://postgres@localhost:5432/sgrs
export SGRS_DEV_ECHO_OTP=1          # el código de ingreso se muestra en pantalla (solo desarrollo)
python -m app.migrate               # crea o actualiza el esquema
uvicorn app.main:app --reload       # http://localhost:8000
```

Con Docker: `cp .env.example .env` (cambia los secretos) y `docker compose --env-file .env up --build`.

## Pruebas
```bash
python -m pytest -q                 # 100+ pruebas; levantan su propio PostgreSQL temporal
python -m scripts.simulate --buyers 40 --seed 7   # simula un sorteo ficticio completo
# E2E con navegador móvil (Playwright):
BASE_URL=http://127.0.0.1:8000 PG_DSN=$SGRS_DSN node e2e/e2e.mjs
```
Cubren concurrencia (30 compradores sobre la misma boleta → uno gana), permisos, expiraciones, límites de abuso, migraciones, WhatsApp simulado, observabilidad y el recorrido completo en navegador.

## Configuración
Variables principales (lista completa en [`docs/DEPLOY_VERCEL.md`](docs/DEPLOY_VERCEL.md)):

| Variable | Para qué |
|---|---|
| `SGRS_DSN` / `DATABASE_URL` | Conexión a PostgreSQL (se detecta también con prefijos de integraciones) |
| `SGRS_ENV=production` | Modo producción (JWT derivado, consentimiento obligatorio, pool) |
| `SGRS_AUTO_SCHEMA=1` | Aplica migraciones al arrancar |
| `SGRS_STORAGE=db` | Comprobantes e imágenes en PostgreSQL (necesario en serverless) |
| `SGRS_BETA_KEY` | Clave de invitación de la beta cerrada |
| `SGRS_DEV_ECHO_OTP=1` | Código en pantalla (solo beta; exige `SGRS_BETA_KEY` en producción) |
| `WHATSAPP_*` | Credenciales de la Cloud API (ver [`docs/WHATSAPP.md`](docs/WHATSAPP.md)) |
| `CRON_SECRET` | Protege `/api/v1/cron/tick` |
| `SENTRY_DSN` | Captura de errores opcional |

## API
REST bajo `/api/v1`. Principales rutas: `auth/otp/*`, `raffles` (crear, publicar, cerrar, sortear), `raffles/{id}/board` (estado compacto), `raffles/{id}/reservations`, `transactions/{id}/approve|reject`, `uploads/proof|image`, `raffles/{id}/accounting`, `s/{código}` (salas), `health`. Documentación interactiva en `/docs` (OpenAPI de FastAPI) con el servidor en marcha.

## Documentación
| Documento | Contenido |
|---|---|
| [`docs/CROWDFUNDING.md`](docs/CROWDFUNDING.md) | Enfoque crowdfunding: marco legal, producto, modelo de datos y fases |
| [`docs/PASARELA.md`](docs/PASARELA.md) | Análisis de pasarelas de pago y recomendación por fases |
| [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) | Flujo, datos, contenedores e interfaz |
| [`docs/DEPLOY_VERCEL.md`](docs/DEPLOY_VERCEL.md) | Despliegue, variables y operación |
| [`docs/WHATSAPP.md`](docs/WHATSAPP.md) | Plantillas y puesta en marcha de WhatsApp Business |
| [`docs/DIAGNOSTICO.md`](docs/DIAGNOSTICO.md), [`docs/PLAN_MEJORAS.md`](docs/PLAN_MEJORAS.md) | Diagnóstico técnico y plan de mejoras ejecutado |
| [`docs/mockup.html`](docs/mockup.html) | Maqueta interactiva sin backend |

## Hoja de ruta
Resumen (detalle en los *issues* del repositorio): modo campaña (donación y recompensas) → niveles, actualizaciones y muro de aportantes → pasarela del creador con conciliación → verificación de creadores → módulo de rifas solo para creadores con autorización verificada.

## Aviso legal
Los textos de términos y privacidad de la aplicación son un **borrador sin revisión jurídica**. Las rifas y los juegos de suerte y azar requieren autorización previa en Colombia (Ley 643 de 2001); el crowdfunding de inversión es una actividad regulada. Consulta a un abogado antes de operar con usuarios reales.

## Licencia
Todos los derechos reservados © [TITULAR]. Pendiente de definir la licencia comercial.
