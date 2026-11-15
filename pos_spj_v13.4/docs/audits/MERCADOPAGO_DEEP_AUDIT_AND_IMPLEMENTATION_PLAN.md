# Auditoría profunda e implementación — Mercado Pago unificado

**Repositorio:** `jarralfa-max/pos_spj_v13.4`  
**Base auditada:** `43ad8d355c8e4b58f1e9a074cf4743c451fc5d3a`  
**Rama de trabajo:** `feat/mercadopago-unified-payments`  
**Fecha:** 2026-11-15  
**Estado:** auditoría estática inicial y plan técnico; no habilitar producción hasta completar pruebas sandbox y revisión de cuenta/terminal.

## 1. Alcance confirmado

- POS: cobro con QR y terminal física Mercado Pago Point.
- WhatsApp: permitir pago total o anticipo configurable por pedido; la liquidación restante se registra como un segundo pago asociado al mismo pedido/venta.
- Mantener la arquitectura actual de SPJ POS v13.4, la BD SQLite canónica, AppContainer, SalesService, servicios de finanzas/caja, reservas de stock, eventos y microservicio WhatsApp.
- No duplicar la lógica de pagos entre POS y WhatsApp.

## 2. Hallazgos confirmados en el código

### P0 — Seguridad y corrección del dinero

1. `pos_spj_v13.4/services/mercado_pago_service.py`
   - Usa `POST /checkout/preferences` (flujo clásico) para crear links.
   - `_headers()` genera un UUID idempotente nuevo en cada llamada. No permite reintentar de forma segura una operación ya intentada.
   - Si falta el token, `_link_sandbox()` devuelve una URL ficticia con dominio real de Mercado Pago. Esto puede confundirse con un cobro real; debe sustituirse por un adaptador sandbox explícito y nunca simular un link productivo.
   - `_get_token()` captura el token una sola vez en el constructor; cambios posteriores de configuración no se reflejan en la instancia.
   - `_guardar_link()` usa `INSERT OR REPLACE` sobre `links_pago`, lo que puede reemplazar el rastro de un intento anterior.
   - `procesar_webhook()` acepta payload sin verificar firma, ignora estados no aprobados y mezcla la confirmación de intención POS con pedidos WhatsApp legacy.
   - Actualiza `links_pago` antes de completar la confirmación de la venta; un fallo posterior puede dejar el pago marcado sin que la venta quede confirmada.
   - `MPWebhookHandler.do_POST()` responde 200 antes de validar/procesar el cuerpo.

2. `whatsapp_service/webhook/mercadopago.py`
   - No valida `x-signature` y `x-request-id`.
   - Procesa únicamente `payment.created`; el flujo nuevo de Orders requiere suscribir y procesar el tópico `orders`.
   - Trata `external_reference` como teléfono y busca la última venta pendiente por coincidencia parcial de teléfono. La referencia externa debe identificar de forma única un intento de pago, sin PII.
   - La idempotencia usa `venta_id + monto`, no el identificador único de la transacción; dos pagos legítimos por el mismo monto podrían colisionar.
   - La notificación al cliente/eventos puede ocurrir aunque la confirmación de negocio no haya terminado correctamente.

3. `whatsapp_service/config/settings.py`
   - `MP_ACCESS_TOKEN` y `MP_WEBHOOK_SECRET` solo se leen de variables de entorno; el POS obtiene token desde `configuraciones.mp_access_token`. Hay dos fuentes de configuración que deben unificarse o leerse mediante una interfaz compartida segura.
   - La BD canónica ya está definida como `pos_spj_v13.4/data/spj_pos_database.db`; el microservicio no debe crear otra BD para pagos.

### P1 — Integración incompleta

4. `pos_spj_v13.4/core/app_container.py`
   - Instancia `MercadoPagoService` y lo inyecta en `SalesService`; es el punto correcto para inyectar el nuevo servicio central y adaptadores.
   - El servicio actual se describe como pagos digitales por link; no se encontró integración de terminal Point Orders ni configuración de terminales/cajas Mercado Pago.

5. `pos_spj_v13.4/modulos/ventas.py` y `core/services/sales_service.py`
   - Ya existe el patrón correcto de intención pendiente: `create_pending_payment_sale()`, reserva temporal de stock y confirmación mediante `confirm_pending_payment_sale()`.
   - La venta definitiva se debe ejecutar solo tras comprobar pago acreditado y conciliar importe/referencia.
   - No sustituir esta ruta por escritura directa en tablas ni por una venta ejecutada al crear el QR/link.
   - La UI de checkout debe ofrecer QR/Point y reflejar estados asincrónicos sin abrir cajón ni emitir `VENTA_COMPLETADA` antes de confirmación.

6. `whatsapp_service/flows/pago_flow.py` y `pos_spj_v13.4/services/bot_pedidos.py`
   - Hay caminos separados que generan preferencias/links. Deben delegar en la misma interfaz de pagos.
   - El diálogo actual contempla efectivo/tarjeta/link; falta una política configurable por pedido para pago total o anticipo.
   - El webhook actual vincula por teléfono, no por intento/pedido único.

7. Trazabilidad financiera
   - `docs/architecture/FINANCIAL_TRACEABILITY_END_TO_END.md` ya define que no debe reconocerse ingreso cuando se crea el link, sino al confirmar el pago; también documenta la comisión MP y la cuenta `6108 Comisiones`.
   - La confirmación financiera debe integrarse con el handler/servicio canónico existente y generar un movimiento por transacción, no por notificación repetida.
   - La comisión real debe tomarse del detalle/settlement devuelto por Mercado Pago cuando esté disponible; no codificar una tasa fija como valor real.

## 3. Decisión de integración Mercado Pago

Usar Orders API como interfaz de integración nueva, con un adaptador para compatibilidad temporal con links clásicos existentes. La documentación actual de Mercado Pago recomienda Orders API para Checkout Pro y también la utiliza para Point; para Point el backend crea una order que se envía a la terminal configurada en modo PDV.

Referencias oficiales:
- Checkout Pro Orders API: https://www.mercadopago.com.mx/developers/es/reference/online-payments/checkout-pro-orders/overview
- Point Orders API y migración: https://www.mercadopago.com.mx/developers/es/docs/mp-point/resources/migrate-payment-intent-to-orders
- Point processing: https://www.mercadopago.com.mx/developers/es/docs/mp-point/payment-processing
- Webhooks y firma: https://www.mercadopago.com.mx/developers/es/docs/checkout-pro-orders/resources/notifications/webhooks

### Canales

- **WhatsApp pago total:** crear un intento `checkout_online` por el total del pedido; enviar `checkout_url`; no confirmar pedido/venta hasta webhook validado y consulta server-to-server.
- **WhatsApp anticipo:** crear intento `checkout_online` por el anticipo calculado/configurado; confirmar el anticipo y registrar saldo pendiente. La liquidación crea un segundo intento distinto ligado al mismo pedido, con su propio ID, importe e idempotency key.
- **POS Point:** crear una order `type=point` con `config.point.terminal_id`, `transactions.payments[].amount`, `external_reference` opaca única y `X-Idempotency-Key`; consultar/recibir webhook del tópico `orders` y conciliar el estado final.
- **POS QR:** investigar y seleccionar el producto/API de QR de cobro para comercio aplicable a México antes de escribir el adaptador. La página pública encontrada bajo `qr-code-ca` documenta cash-outs/retiros, no debe confundirse con cobro de venta. Point Orders admite `config.payment_method.default_type=qr` para terminales PDV; esto permite QR en la terminal, pero no demuestra por sí solo que se pueda mostrar un QR dinámico de cobro en la pantalla del POS. Mantener esta diferencia como gate técnico explícito.
- **No usar el SDK como requisito arquitectónico:** Orders API puede consumirse por HTTP desde un cliente aislado; incorporar SDK oficial solo si su versión soporta exactamente los endpoints/validación requeridos. No mezclar SDK, HTTP ad hoc y llamadas de negocio en UI.

## 4. Arquitectura objetivo

```
POS UI ─────────────┐
                    ├── PaymentApplicationService
WhatsApp Flow ──────┘          │
                               ├── PaymentProvider (MercadoPagoOrdersClient)
                               ├── PaymentRepository (intentos/transacciones)
                               ├── PaymentPolicy (total/anticipo/saldo)
                               └── PaymentConfirmationHandler
                                         │
Webhook FastAPI (/webhook/mercadopago)
  ├─ validar firma HMAC x-signature + x-request-id + data.id
  ├─ registrar evento entrante/idempotente
  ├─ consultar order/payment en MP (no confiar en payload)
  ├─ verificar estado, moneda, importe, referencia y cuenta
  └─ aplicar transición transaccional
       ├─ POS: SalesService.confirm_pending_payment_sale()
       ├─ WhatsApp: confirmar anticipo o pedido/saldo
       ├─ FinanceService / ledger / comisión real
       ├─ eventos de dominio / notificación cliente
       └─ liberar/cancelar reserva al expirar o cancelar
```

El webhook debe ser rápido y durable: validar firma, persistir evento pendiente y responder 200 solo después de guardar el evento; procesar la conciliación en un worker/outbox reintentable. Si no se puede persistir, responder error para que Mercado Pago reintente.

## 5. Modelo de datos propuesto (migración aditiva)

No reutilizar `links_pago` como tabla financiera única. Preservarla para compatibilidad y crear entidades explícitas:

- `payment_intents`: id interno UUID, source_channel (pos/whatsapp), source_type (sale/order), source_id/folio, purpose (full/advance/balance), amount, currency, status, provider, provider_order_id, checkout_url, external_reference, idempotency_key, branch_id, cashier/user, expires_at, timestamps.
- `payment_transactions`: provider_transaction_id único, intent_id, amount, currency, status, payment_method/type, fee, net_amount, provider_payload_redacted, timestamps.
- `payment_webhook_events`: provider_event_id/event key único, topic, resource_id, request_id, signature_valid, processing_status, attempts, received_at, processed_at, error_code.
- `payment_terminal_configs`: branch_id, caja_id, terminal_id, external_pos_id, operating_mode, enabled, metadata no sensible.
- Índices únicos por `provider_transaction_id`, `external_reference`, `idempotency_key` y por evento según esquema de MP.
- Guardar solo datos mínimos; no almacenar PAN/CVV ni credenciales dentro de estas tablas.

El nombre/tipo real de IDs debe respetar UUIDv7/TEXT y sucursal como TEXT en el esquema canónico actual. La migración debe ser incremental, compatible con SQLite y reversible mediante backup/restauración; no cambiar tablas legacy existentes en esta fase.

## 6. Reglas críticas de negocio

1. La referencia externa identifica un intento específico, nunca teléfono, email ni PII.
2. Un pago se aplica como máximo una vez por ID de transacción Mercado Pago.
3. Una notificación no es evidencia de pago: consultar el recurso en Mercado Pago y verificar estado terminal aprobado/procesado, importe exacto, moneda MXN, external_reference y cuenta receptora.
4. Pago parcial: no marcar pedido liquidado; acumular pagos aprobados hasta cubrir el saldo. Rechazado/cancelado/expirado no genera ingreso ni venta pagada.
5. No permitir dos intentos activos incompatibles para el mismo saldo; usar transacción/locking y expiración.
6. Un cobro POS Point no ejecuta la venta hasta resultado final confirmado. Cancelación y timeout dejan el checkout en estado recuperable; reconciliar antes de permitir nuevo cobro.
7. Refunds/chargebacks generan reversas vinculadas a transacción original, no borrado/edición del pago original.
8. El corte de caja distingue efectivo, Point, QR y checkout online; los pagos digitales no inflan efectivo en caja.
9. Comisiones y neto se concilian con importes reales del proveedor; no asumir 3.6% fijo.
10. No fallback silencioso a sandbox ni marcar como pagado cuando no haya token/webhook/consulta válida.

## 7. Plan de ejecución

### Fase A — Baseline y pruebas de regresión
- Obtener el árbol y commit actual; ejecutar pruebas específicas de Mercado Pago, SalesService, WhatsApp, finanzas y caja.
- Confirmar las tablas reales y migraciones existentes; identificar flujos legacy aún activos.
- Añadir pruebas de contrato antes de modificar comportamiento.

### Fase B — Núcleo unificado
- Implementar cliente Orders API con timeout, manejo de errores, idempotencia estable por operación, consulta/cancelación/refund.
- Implementar PaymentRepository y migración aditiva.
- Mantener fachada `MercadoPagoService` temporal como adapter/delegator para no romper imports legacy.

### Fase C — Webhooks
- Un solo endpoint de webhook para tópicos `orders` y pagos online aplicables.
- Validación HMAC con `x-signature`, `x-request-id`, `data.id` y secreto de webhook.
- Persistencia de eventos, worker/outbox, replay seguro y conciliación server-to-server.
- Eliminar la búsqueda por teléfono y las confirmaciones duplicadas entre microservicio y POS.

### Fase D — Canales
- POS: Point Orders, selección terminal por sucursal/caja y estado de order en UI.
- POS: QR dinámico de cobro en pantalla solo tras validar la API de merchant collections para MX; habilitar QR en Point terminal cuando cuenta/modelo lo soporte.
- WhatsApp: opciones pago total/anticipo configurables, link de checkout, confirmación automática y liquidación con segundo intento.

### Fase E — Finanzas, caja y operación
- Integrar pagos aprobados, comisiones reales, neto, reembolsos, conciliación y cortes.
- Panel de configuración para token, secreto webhook, terminales/cajas y política de anticipo.
- Observabilidad sin exponer tokens ni payloads sensibles.

### Fase F — Validación
- Pruebas unitarias y de integración con sandbox/usuarios de prueba.
- Pruebas de duplicación/reintentos, importe distinto, moneda incorrecta, evento fuera de orden, pago parcial, expiración, cancelación, refund, caída de red y webhook falso.
- Pruebas de regresión POS/WhatsApp/inventario/caja y revisión del diff.
- No activar producción hasta recibir credenciales/secretos configurados por el usuario y validar Point terminal en cuenta real controlada.

## 8. Criterios de aceptación

- Una sola transacción aprobada crea un único movimiento financiero y una sola confirmación de venta/pedido.
- Repetir el webhook 10 veces no duplica ventas, anticipos, inventario, puntos ni ingresos.
- Importe/moneda/referencia no coincidentes nunca se aplican.
- POS QR y POS Point muestran estado pendiente/aprobado/rechazado/cancelado y no finalizan venta prematuramente.
- WhatsApp puede cobrar total o anticipo y después liquidar el saldo con un segundo pago trazable.
- Cada transacción está ligada a sucursal, caja, usuario, pedido/venta, folio e ID de proveedor.
- Reportes/cortes separan cobros digitales y efectivo.
- Los flujos legacy siguen funcionando durante migración, sin enlaces sandbox falsos ni doble webhook.

## 9. Riesgos/gates abiertos

- Confirmar en cuenta Mercado Pago México si el QR dinámico de cobro merchant/collections puede mostrarse en pantalla POS bajo el producto contratado; no reutilizar documentación de cash-out.
- Confirmar modelos/seriales de terminales Point y asociación de cada terminal a una caja/sucursal de Mercado Pago, modo PDV.
- Confirmar si la cuenta está configurada para OAuth/una sola cuenta de vendedor; si JUANIS usa una sola cuenta, token de vendedor protegido en configuración cifrada/secret store. No pedir ni incluir credenciales en commits.
- La auditoría aquí es estática contra archivos del repositorio; no se ha ejecutado la suite completa ni llamadas de cobro reales.
