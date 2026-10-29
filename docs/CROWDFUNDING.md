# Plan de desarrollo: enfoque crowdfunding

> No es asesoría jurídica. Las referencias normativas salen de búsquedas web (octubre 2026) y deben confirmarse con un abogado antes de operar.

## 1. Por qué cambiar el enfoque
**Rifa** tiene un significado legal preciso en Colombia: es un juego de suerte y azar (Ley 643 de 2001) en el que se sortean premios en especie entre quienes tienen boletas vendidas a precio fijo, y requiere **autorización previa**. Según las fuentes consultadas: Coljuegos autoriza rifas de carácter nacional, ETESA las que operan en dos o más departamentos, y las demás dependen de la autoridad territorial; además hay reglas sobre garantías, publicidad, plazos de entrega de premios y actas del sorteo. Una plataforma que facilita rifas sin que el organizador tenga esa autorización expone a ambos.

**Crowdfunding de donación o de recompensas** es otra figura. El Decreto 1357 de 2018 regula la financiación colaborativa **de inversión** (valores de deuda o capital, bajo vigilancia de la Superintendencia Financiera) y, según lo consultado, **no** regula la de donación ni la de recompensas. Esto debe confirmarse con un concepto vigente.

**Regla de diseño: sin azar y sin rendimientos.**
1. Las recompensas se definen por **nivel de aporte**, nunca por sorteo. Si una recompensa se asigna al azar entre aportantes, vuelve a ser un juego de suerte y azar.
2. No se ofrecen participaciones, utilidades, intereses ni propiedad: eso sería inversión (valores) y entra al régimen financiero.

## 2. Producto
| Tipo | Qué es | Estado |
|---|---|---|
| **Donación** | Apoyo sin contraprestación a una causa o persona | Fase 1 |
| **Recompensas** | Niveles de aporte con una recompensa definida (producto, experiencia, mención) | Fase 1–2 |
| **Preventa** | Recompensa = el producto, con fecha de entrega | Fase 3 |
| ~~Inversión / préstamos~~ | Régimen financiero | **Fuera de alcance** |
| **Rifas / sorteos** | Módulo existente | Opcional, apagado por defecto, solo para creadores con autorización verificada (fase 5) |

### Vocabulario (interfaz, textos y API pública)
| Hoy | Nuevo |
|---|---|
| Rifa | Campaña |
| Organizador | Creador |
| Comprador | Aportante |
| Boleta / número | Aporte / nivel de recompensa |
| Valor de la boleta | Monto del aporte |
| Cierre de ventas | Fecha límite |
| Premio | Recompensa |
| Sorteo | (no aplica; solo en el módulo de rifas) |
| Arqueo | Informe de recaudo |
| Sala | Perfil del creador |

## 3. Funcionalidad del modo campaña
- **Creador:** título, historia, portada y galería (ya existe), enlace a video, categoría, **meta en COP** y **fecha límite**, niveles de recompensa (monto, descripción, cupo opcional, entrega estimada), cuentas de pago.
- **Aportante:** elige un nivel o un monto libre, paga (medio externo y comprobante, o pasarela más adelante), aporta como persona o de forma **anónima** y puede dejar un mensaje.
- **Verificación:** la cola del creador se reutiliza (aprobar/rechazar, reserva con vencimiento).
- **Progreso público:** recaudado frente a la meta, número de aportantes, días restantes, muro de aportantes (respetando el anonimato).
- **Transparencia:** informe de recaudo con huella verificable (ya existe), actualizaciones del creador, estado de entrega de recompensas.
- **Compartir:** enlaces con vista previa y tarjeta de imagen (ya existe), códigos cortos y perfil del creador.
- **Avisos:** agradecimiento al aportante y confirmaciones por WhatsApp (plantillas existentes, textos nuevos).
- **Reglas:** meta cumplida no cierra la campaña salvo que el creador lo decida; campañas «flexibles» (el creador conserva lo recaudado) mientras no haya custodia (ver `PASARELA.md`).

## 4. Qué se reutiliza y qué cambia
Se reutiliza casi todo: usuarios y OTP, transacciones con comprobante y vencimiento, cola de aprobación, auditoría encadenada, imágenes, notificaciones, enlaces para compartir, observabilidad, límites de abuso, migraciones y despliegue.

Datos nuevos (migración `0003`):
```
campaigns      (id, owner_id, kind[DONATION|REWARDS], title, story, goal_amount, currency, deadline_at,
                status[DRAFT|ACTIVE|ENDED|CANCELLED], video_url, category, payment_accounts, visibility, ...)
reward_tiers   (id, campaign_id, amount, title, description, quota NULL, claimed, est_delivery)
pledges        (id, campaign_id, tier_id NULL, backer_id, amount, anonymous, message,
                status[PENDING|CONFIRMED|FULFILLED|REFUNDED|EXPIRED], transaction_id)
campaign_posts (id, campaign_id, title, body, created_at)
```
- `payment_transactions` se generaliza con un `kind` (`TICKETS`/`PLEDGE`) y una tabla puente `pledge_payments`, o se enlaza `pledges.transaction_id`; la aprobación pasa de «boletas a PAGADO» a «aporte a CONFIRMED».
- Cupos de un nivel: decremento atómico (`UPDATE … WHERE claimed < quota`), igual que las boletas.
- El módulo de rifas se mantiene detrás de un interruptor (`SGRS_MODULE_RAFFLES`), apagado en el despliegue público.

## 5. Fases (estimación orientativa, 1 persona)
| Fase | Alcance | Duración |
|---|---|---|
| **0. Ajustes inmediatos** | Vocabulario «campaña» en la interfaz y los textos; términos que prohíben premios por azar y rendimientos; declaración del creador al crear; interruptor para ocultar rifas | 3–5 días |
| **1. MVP campaña** | Migración `0003`; crear/publicar campaña con meta y fecha; aportar con comprobante; aprobación; progreso público; informe de recaudo; pruebas y E2E | 3–4 semanas |
| **2. Comunidad** | Niveles con cupo, actualizaciones, muro de aportantes, anonimato, entrega de recompensas, exportación CSV, agradecimientos por WhatsApp | 2–3 semanas |
| **3. Pagos** | Pasarela del creador (modelo 1 de `PASARELA.md`), conciliación, reembolsos registrados | 3–4 semanas |
| **4. Confianza** | Verificación ligera del creador, reporte de campañas, moderación, métricas de transparencia | 2–3 semanas |
| **5. Rifas verificadas** (opcional) | Habilitar el módulo solo a creadores que adjunten su autorización vigente (número y documento revisados) | 1–2 semanas |

## 6. Cambios de bajo riesgo para hacer ya (fase 0)
1. Cambiar el texto visible de «rifa/boleta/sorteo» por «campaña/aporte/recompensa» en los flujos nuevos.
2. Términos: la plataforma no organiza ni autoriza juegos de suerte y azar; está prohibido ofrecer premios por sorteo sin la autorización legal; no se admiten promesas de rendimiento o participación.
3. Casilla del creador al publicar: «Declaro que mi campaña no ofrece premios por azar ni rendimientos económicos».
4. Ocultar el módulo de rifas por defecto en producción.

## 7. Preguntas para el abogado
- ¿La actividad (campañas de donación y recompensas, sin custodia) requiere alguna autorización o registro?
- ¿Los «sorteos entre aportantes» como incentivo caen en juegos promocionales (autorización previa) o en rifas?
- ¿Qué cláusulas deben tener los términos y la política de privacidad (Ley 1581 de 2012) y la relación con el consumidor en las recompensas (Ley 1480 de 2011)?
- Tributación de donaciones y recompensas para creadores y para la plataforma si cobra comisión.
- Prevención de lavado de activos y financiación del terrorismo para plataformas de campañas.
- Responsabilidad por contenido y campañas fraudulentas; procedimiento de retiro.

## 8. Métricas de éxito
Campañas publicadas y activas · % que alcanza su meta · tiempo de verificación de un aporte · aportes por campaña · conversión del enlace al aporte · tasa de rechazo y de vencimiento · campañas reportadas.

## 9. Fuentes
- [Reglamentan financiación colaborativa (Valora Analitik)](https://www.valoraanalitik.com/?p=11649) · [Crowdfunding en Colombia (Brigard Urrutia)](https://www.bu.com.co/es/insights/noticias/crowdfunding-en-colombia) · [Concepto de la Superfinanciera (Ámbito Jurídico)](https://www.ambitojuridico.com/sites/default/files/BancoMedios/Archivos/cpto-9738-19.pdf)
- [Requisitos de rifas nacionales (Coljuegos)](https://www.coljuegos.gov.co/descargar.php?id=200057) · [Decreto 1486 de 2024 (DIAN)](https://normograma.dian.gov.co/dian/compilacion/docs/decreto_1486_2024.htm) · [Decreto 493 de 2001 (juegos promocionales)](https://www1.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=6088) · [Decreto 2104 de 2016](https://www.ambitojuridico.com/sites/default/files/BancoMedios/Archivos/d-2104-16.pdf)
