# Diagnóstico técnico (29 oct 2026)

Alcance: código en `main` (commit `9d9d7f5`), despliegue de producción en Vercel + Neon, y mediciones locales.
Las cifras de rendimiento son **locales** (PostgreSQL 16 en la misma máquina, 4 procesos); en Vercel + Neon habrá latencia de red adicional y no se midió.

## 1. Estado
| Verificación | Resultado |
|---|---|
| Pruebas automáticas | 74 pasan; cobertura de `app/` **92 %** (el worker queda sin cubrir) |
| E2E en navegador móvil (36 comprobaciones) | Pasan, incluida una configuración tipo Vercel (BD vacía, esquema automático, comprobantes en BD) |
| Dependencias vulnerables (`pip-audit`) | Ninguna conocida |
| Análisis estático (`bandit`) | 0 altos. 9 avisos medios, todos falsos positivos: SQL con fragmentos constantes (nunca datos del usuario) y la palabra `bearer` |
| Estilo (`ruff`) | 73 avisos, casi todos el patrón `Depends()` de FastAPI; 2 imports sin usar y 3 `raise` sin `from` |
| Producción: base de datos | **Conectada**: una consulta devuelve `CODE_NOT_FOUND` (antes `DB_NOT_CONFIGURED`) |
| Producción: acceso | **Bloqueado**: `/api/v1/auth/config` responde `beta:false, otp_on_screen:false`. Falta `SGRS_BETA_KEY`; sin ella nadie recibe código y el login responde 502 (comportamiento seguro buscado) |
| Cabeceras de seguridad en producción | CSP estricta, HSTS, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `X-Robots-Tag: noindex` presentes |

## 2. Mediciones (local, 20 000 boletas)
| Operación | Resultado |
|---|---|
| Publicar rifa de 20 000 boletas | 0,8 s |
| `GET /raffles/{id}/tickets` | 295–430 ms, **2,2 MB** (571 KB comprimido) por petición |
| Reserva (1 boleta) | 64 ms secuencial; 112 req/s con 10 en paralelo; 102 req/s con 50 (p95 560 ms) |
| Aprobación | 109–135 req/s con 20 en paralelo |
| Consulta de boletas (`EXPLAIN`) | 43 ms de ejecución, usa los índices |
| Bloqueo global de auditoría (`LOCK TABLE audit_log`) | Costo medido ≈ 3–10 %: hoy no es cuello de botella |
| Concurrencia sobre la misma boleta | 30 compradores simultáneos → exactamente 1 gana (prueba automática) |

Nota de método: en este entorno los clientes HTTP pasan por un proxy; las primeras mediciones (16 req/s) eran un artefacto y se descartaron al repetirlas sin proxy.

## 3. Hallazgos y mejoras

> **Estado de ejecución (ver `PLAN_MEJORAS.md`):** P0.2, P0.3, P0.4, P1.5, P1.6, P1.7, P1.9 y P2.12/13/14 implementados y probados. Quedan: P0.1 (variable de entorno, acción tuya), P1.8, P1.10, P2.11, P2.15 y P2.16.


### P0: antes de invitar testers
1. **Definir `SGRS_BETA_KEY` y redesplegar** (producción bloqueada por diseño sin ella).
2. **Migraciones de esquema.** `SGRS_AUTO_SCHEMA` solo crea tablas en una base *vacía*. Cualquier cambio posterior de esquema (ya hubo dos) no se aplicaría en Neon. Introducir una tabla `schema_migrations` y archivos SQL numerados aplicados al arrancar (≈ medio día). Hacerlo antes de tener datos reales.
3. **Notificaciones de WhatsApp en Vercel Hobby.** El envío de la cola solo corre en el cron (una vez al día); el mantenimiento perezoso no la procesa. Al configurar WhatsApp, los avisos llegarían con hasta 24 h de retraso. Procesar unos pocos mensajes en el mantenimiento perezoso o tras responder (≈ 2 h).
4. **Textos legales.** No hay aviso de privacidad ni términos de la plataforma (datos personales de celular y comprobantes). Necesario antes de usuarios externos; consultar con un abogado.

### P1: antes de abrir a más usuarios
5. **Carga de la grilla.** Cada visitante descarga la lista completa de boletas cada 5 s: 2,2 MB con 20 000. Una rifa de unas 40 000 boletas superaría el límite de 4,5 MB de respuesta de las funciones y fallaría. Mejoras: formato compacto (arreglo de estados en vez de objetos), `ETag`/`304`, sondeo incremental con versión de la rifa, o paginar por rangos; cuando solo se pinta lo visible, bajar la frecuencia a 10–15 s.
6. **Conexión a la base por petición.** Cada petición abre una conexión nueva a Neon (en red real suma decenas de ms). Reutilizar un pool por instancia (`psycopg_pool`) con el pooler de Neon.
7. **Límites de abuso.** El reintento de OTP se limita por número, no por IP; la clave de beta no tiene límite de intentos; cualquier usuario puede crear rifas ilimitadas. Añadir reglas de límite de tasa en el firewall de Vercel y un tope de rifas por usuario.
8. **Sesión.** JWT de 8 h en `localStorage`, sin revocación. Mitigado con CSP estricta; añadir refresh token y cierre de sesión en servidor.
9. **Observabilidad.** Los registros de Vercel Hobby duran 1 hora y no hay captura de errores ni alertas. Añadir Sentry (o similar), un chequeo externo de disponibilidad sobre `/api/v1/auth/config` y registros estructurados.
10. **Respaldo y capacidad de Neon.** Verificar la ventana de restauración del plan gratuito y el crecimiento: los comprobantes viven en la base (límite de 4 MB; ≈ 300 KB típicos tras la reducción en el cliente). Al acercarse al límite del plan, pasarlos a almacenamiento de objetos privado.

### P2: calidad y evolución
11. **Auditoría con bloqueo global.** Hoy cuesta poco; con cientos de escrituras por segundo conviene encadenar el hash por rifa en lugar de globalmente.
12. **Verificación de la cadena de auditoría** (`verify_chain`) existe pero no se expone ni se ejecuta periódicamente: añadirla al cron y a un reporte para el administrador.
13. **Pruebas.** Añadir una prueba de carga corta en CI, pruebas de accesibilidad automáticas (axe) y cubrir `worker.py`.
14. **Limpieza menor.** Quitar 2 imports sin usar, usar `raise … from None`, mover imports de `main.py` al inicio.
15. **Experiencia.** Rifas de miles de boletas: buscador por rango y "elegir al azar N números"; formulario de creación más corto (pasos); vista previa de cómo verán la rifa los compradores.
16. **Equivalencia local/nube.** Docker Compose y el job E2E del CI nunca se ejecutaron en un entorno con Docker: validarlos.

## 4. Plan de pruebas con usuarios reales (beta cerrada)
- **Perfiles:** 2–3 organizadores y 8–10 compradores, con pagos ficticios.
- **Tareas guiadas:** crear una rifa con portada; compartir por enlace y por código; comprar con comprobante desde un celular de gama baja y datos móviles; verificar y aprobar; cierre y sorteo; ver el resultado.
- **Métricas:** éxito por tarea, tiempo para crear una rifa y para comprar, errores mostrados, abandono en el login y en el pago, y dispositivos/navegadores.
- **Datos a observar en el sistema:** transacciones vencidas, rechazos, tiempo entre reporte y aprobación, conflictos de boletas (`409`), tamaño de comprobantes.
- **Criterio de salida:** ≥ 90 % de tareas completadas sin ayuda, cero pérdida de datos, cero accesos cruzados entre cuentas.

## 5. Orden sugerido
1) P0.1 y P0.2 → 2) P0.3 → 3) P1.5, P1.6, P1.7 → 4) P1.9 → 5) resto según lo que muestre la beta.
