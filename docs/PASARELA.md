# Análisis de pasarela de pagos

> Las cifras y afirmaciones sobre proveedores y regulación provienen de búsquedas web y prensa (octubre 2026). **Verifícalas con cada proveedor y con asesoría legal antes de decidir.** Esto no es asesoría jurídica ni financiera.

## 1. Punto de partida
Hoy la plataforma **no mueve dinero**: el aportante paga directo al organizador (Nequi, Daviplata, Bre-B, PayPal…), sube un comprobante y el organizador lo valida a mano. Es un libro de control con auditoría.

| Ventaja | Límite |
|---|---|
| Sin riesgo regulatorio de custodia, sin costos de pasarela, listo ya | Verificación manual (tiempo, error humano) |
| Funciona con cualquier medio de pago | Comprobantes falsificables; la prueba es una imagen |
| El organizador cobra al instante | No hay conciliación automática ni reembolsos gestionados |

**Qué resolvería una pasarela:** verificación automática (webhook en lugar de revisar imágenes), menos fraude de comprobantes, pago con tarjeta/PSE (más confianza y conversión), conciliación y reportes.

## 2. Tres modelos de integración
| Modelo | Quién recibe el dinero | La plataforma… | Riesgo regulatorio | Recomendación |
|---|---|---|---|---|
| **0. Manual (actual)** | El organizador, directo | Solo registra y audita | Mínimo | Mantener como respaldo siempre |
| **1. Pasarela del organizador** | El organizador, en su propia cuenta de pasarela | Crea el cobro con las credenciales del organizador y recibe el webhook de confirmación; nunca toca fondos | Bajo: es software, no recauda | **Fase siguiente** |
| **2. Marketplace / split** | La plataforma (comercio principal) y reparte a organizadores | Cobra y liquida a terceros | Alto: recaudar y transferir fondos de terceros puede acercarla a actividades supervisadas (la Superfinanciera autoriza a las sociedades de depósitos y pagos electrónicas, SEDPE, para captar recursos y prestar servicios de pago) | Solo con asesoría legal y un proveedor que asuma el rol regulado |
| **3. Custodia propia** | La plataforma, que luego desembolsa | Custodia dinero ajeno | Muy alto | **Evitar** sin licencia |

Consecuencia de diseño: sin custodia **no se puede retener** el dinero hasta cumplir una meta ni reembolsar desde la plataforma. El esquema «todo o nada» exige custodia (modelo 2/3); mientras tanto, usar campañas «flexibles» (el creador conserva lo recaudado) y que los reembolsos los haga el creador desde su cuenta.

## 3. Proveedores a evaluar (Colombia)
| Proveedor | Métodos reportados | Tarifas reportadas | Split a terceros | Notas |
|---|---|---|---|---|
| **Wompi** (Grupo Cibest/Bancolombia) | Tarjetas, PSE, Nequi, corresponsales | Presencial 1,98 % + IVA; QR 1 % (prensa, sep 2026). Comercio electrónico: confirmar | No encontré documentación pública: preguntar | Gran escala (≈ 40 000 negocios activos al mes según CB Insights); buen candidato por Nequi/PSE |
| **ePayco** | PSE, Gana, Efecty, tarjetas | Histórica 2,99 % + $600 (verificar vigencia) | **«Pagos divididos» lanzado en 2026** (prensa); confirmar en su documentación | Útil si se va al modelo 2 |
| **Mercado Pago** | Tarjetas, PSE y otros | Confirmar | **Split 1:1** con documentación para Colombia | Documentación de marketplace madura |
| **PayU, Bold, otros** | — | — | — | No evaluados a fondo |
| **Bre-B** (Banco de la República) | Pagos inmediatos por «llave» | — | — | 116 millones de llaves y 36 millones de clientes a oct 2026 (prensa). Hoy se usa como pago manual (ya está soportado como plataforma `BREVE`); evaluar si habrá API de iniciación de pagos |

Costos totales a modelar: comisión + IVA + 4×1000 + posibles retenciones + costo de contracargos. Pedir cotización por volumen y por método (PSE y Nequi suelen tener estructuras distintas a tarjeta).

## 4. Criterios de selección
Costo total · métodos (Nequi, PSE, tarjetas, Bre-B) · sandbox y documentación · webhooks firmados e idempotencia · liquidación (T+n) · contracargos · alta de **personas naturales** como comercio (fricción de KYC del creador) · split · soporte en español · estabilidad.

## 5. Diseño técnico propuesto (modelo 1)
Interfaz de proveedor desacoplada, para poder cambiar de pasarela:
```python
class PaymentProvider(Protocol):
    def create_checkout(self, creds, intent) -> CheckoutUrl: ...
    def verify_webhook(self, creds, headers, raw_body) -> bool: ...
    def parse_event(self, raw_body) -> PaymentEvent: ...   # referencia, estado, monto, id externo
    def fetch_status(self, creds, external_id) -> PaymentEvent: ...  # conciliación
```
- **Tabla `payment_intents`** (id, transacción/aporte, proveedor, referencia única, monto, estado `CREATED/PENDING/APPROVED/DECLINED/EXPIRED`, id externo, crudo del último evento). Una referencia por intento, índice único.
- **Webhook** `POST /api/v1/webhooks/pay/{proveedor}`: valida firma con el secreto del organizador, es idempotente (mismo evento dos veces = un efecto), compara monto y referencia con lo esperado y **confirma automáticamente** la transacción (reutiliza la lógica de aprobación actual).
- **Conciliación**: el cron consulta `fetch_status` de las intenciones pendientes con más de X minutos (los webhooks pueden perderse).
- **Credenciales del organizador**: cifradas en reposo a nivel de columna (clave en una variable de entorno o KMS), nunca en registros ni en la API.
- **PCI**: pago en la página **hospedada** del proveedor (SAQ-A); la plataforma jamás ve ni guarda datos de tarjeta.
- **Modo manual conservado**: sigue disponible para medios sin pasarela; el comprobante pasa a ser respaldo.
- **Reembolsos**: se hacen en la pasarela del organizador; la plataforma registra el estado `REFUNDED` por webhook.
- **Pruebas**: proveedor simulado (como el de WhatsApp) con firma y casos de duplicado, monto distinto, evento tardío y webhook perdido.

## 6. Recomendación por fases
1. **Ahora:** modelo 0 con testers. Medir tiempo de verificación y errores del organizador: esa es la métrica que justifica integrar.
2. **Fase de pasarela (modelo 1):** elegir un proveedor tras sandbox y cotización (Wompi o ePayco son los candidatos). 3–4 semanas de trabajo estimadas.
3. **Split/marketplace (modelo 2):** solo con concepto jurídico y contrato con un proveedor que asuma el rol regulado; el beneficio es cobrar comisión por transacción, el costo es el cumplimiento (SARLAFT/prevención de lavado, tratamiento tributario, soporte de disputas).
4. **Seguimiento de Bre-B** para pagos inmediatos nativos.

## 7. Preguntas para el abogado y los proveedores
- ¿Recibir y repartir aportes de terceros (split) obliga a la plataforma a una autorización específica? ¿Basta con que el proveedor sea el agente regulado?
- ¿Qué obligaciones de prevención de lavado de activos aplican a una plataforma de campañas aunque no custodie fondos?
- ¿Cómo tributan los aportes (donación vs ingreso por recompensa) y qué retenciones aplican al creador?
- ¿Aceptan las pasarelas personas naturales sin RUT con actividad de campañas? ¿Qué documentos piden?
- ¿Qué cubre el proveedor en contracargos y fraude, y quién responde, el creador o la plataforma?
- ¿Hay API de Bre-B para iniciar pagos desde un comercio?

## 8. Fuentes consultadas
- [Wompi: tarifas y alcance (Cambio, sep 2026)](https://cambiocolombia.com/peso-a-peso-paso-a-paso/articulo/2026/9/wompi-amplia-los-pagos-sin-contacto-y-baja-al-uno-por-ciento-la-tarifa-de-los-pagos-con-qr) · [Wompi (CB Insights)](https://www.cbinsights.com/company/wompi) · [Wompi en Shopify](https://apps.shopify.com/wompi-pagos?locale=es)
- [ePayco lanza pagos divididos (2026)](https://www.descubre.vc/noticia/epayco-lanza-pagos-divididos-para-optimizar-el-flujo-de-caja-en-colombia-2026-05-19) · [Mercado Pago: split 1:1](https://www.mercadopago.com.co/developers/es/docs/split-payments/split-1-1/overview)
- [Bre-B: primer año (El País, oct 2026)](https://www.elpais.com.co/economia/en-su-primer-ano-bre-b-mueve-262-billones-y-alcanza-116-millones-de-llaves-en-colombia-0604.html)
- [Sociedades especializadas en depósitos y pagos electrónicos (La República)](https://www.larepublica.co/sociedades-especializadas-en-depositos-y-pagos-electronicos)
