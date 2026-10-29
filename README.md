# Rifa_app (SGRS)

Sistema de Gestión de Rifas y Sorteos: libro mayor de reservas y pagos externos (FastAPI + PostgreSQL).

- `schema.sql`: esquema PostgreSQL 16.
- `app/`: API (reservas, aprobación, rechazo, expiración).
- `tests/`: pruebas, incluida concurrencia (`python3 -m pytest -q`).

Variables: `SGRS_DSN`, `SGRS_JWT_SECRET` (obligatoria en producción).
