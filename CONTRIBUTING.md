# Contribuir

1. **Antes de empezar**, abre o comenta un *issue* para acordar el alcance.
2. **Ramas:** una rama por cambio (`feat/…`, `fix/…`); los cambios entran a `main` por *pull request*.
3. **Esquema:** todo cambio de base de datos es un archivo nuevo `migrations/NNNN_nombre.sql`; nunca se edita uno ya publicado.
4. **Pruebas:** `python -m pytest -q` debe pasar; añade pruebas del comportamiento nuevo. Si tocas la interfaz, ejecuta también `e2e/e2e.mjs`.
5. **Estilo:** `ruff check app`; textos de interfaz en español, sencillos y sin tecnicismos.
6. **Seguridad y datos:** no registres celulares ni comprobantes en logs; no subas secretos (usa `.env`, ignorado por git).
7. **Cambios de textos legales:** actualiza `TERMS_VERSION` en `app/legal.py` para pedir una nueva aceptación.
