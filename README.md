# Rifa_app (SGRS)

Sistema de Gestión de Rifas y Sorteos: libro mayor de reservas y pagos externos (FastAPI + PostgreSQL).

- `schema.sql`: esquema PostgreSQL 16.
- `app/`: API (reservas, aprobación, rechazo, expiración).
- `tests/`, `scripts/simulate.py`: pruebas y simulación de sorteos ficticios.
- `docs/ARQUITECTURA.md` y `docs/sgrs-flujo.bpmn`: flujo, datos y despliegue.

Variables: `SGRS_DSN`, `SGRS_JWT_SECRET` (obligatoria en producción).
