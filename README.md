# Rifa_app (SGRS)

Sistema de Gestión de Rifas y Sorteos: libro mayor de reservas y pagos externos (FastAPI + PostgreSQL).

- `migrations/`: esquema PostgreSQL 16 versionado (`python -m app.migrate`).
- `app/`: API (reservas, aprobación, rechazo, expiración).
- `tests/`, `scripts/simulate.py`: pruebas y simulación de sorteos ficticios.
- `docs/ARQUITECTURA.md` y `docs/sgrs-flujo.bpmn`: flujo, datos y despliegue.

Variables: `SGRS_DSN`, `SGRS_JWT_SECRET` (obligatoria en producción).
