# Auditoría profunda y plan de implementación — Mercado Pago unificado

Fecha: 2026-11-15
Base auditada: `main` en `43ad8d355c8e4b58f1e9a074cf4743c451fc5d3a`
Rama de preparación: `feat/mercadopago-unified-payments`

## 1. Alcance y conclusión

Revisión estática focalizada de los módulos de pago POS, WhatsApp, ventas, contabilidad, contenedor, migraciones y pruebas. No se ejecutó el ERP ni la suite de pruebas en esta auditoría. Esta rama contiene este documento de auditoría/plan; todavía no modifica código de producción ni credenciales.

La base existente es aprovechable: el POS ya crea intenciones pendientes y reserva inventario mediante `SalesService`; la confirmación puede terminar en `execute_sale_result`; existe un `MercadoPagoService` con Checkout Preferences y consulta de pagos; WhatsApp tiene flujo de link y un webhook propio. El problema principal no es ausencia total de integración, sino que los canales y sus webhooks no comparten un ciclo de vida de pago seguro y consistente.

## 2. Arquitectura detectada

- `core/app_container.py` instancia `MercadoPagoService` y luego inyecta `sales_service`.
- `core/services/sales_service.py` implementa `create_pending_payment_sale`, `confirm_pending_payment_sale` y cancelación/expiración de intenciones; la intención conserva contexto y reserva de stock.
- `services/mercado_pago_service.py` crea Checkout Preferences, consulta `GET /v1/payments/{id}` y actualiza `links_pago`. Su `X-Idempotency-Key` actual es UUID nuevo por request.
- `modulos/ventas.py` ya tiene una ruta para iniciar pago Mercado Pago como venta pendiente; la selección del método y el cierre de checkout viven en la UI PyQt.
- `whatsapp_service/flows/pago_flow.py` contiene un segundo creador de preferencias, independiente del servicio ERP.
- `whatsapp_service/webhook/mercadopago.py` recibe notificaciones, consulta el pago a Mercado Pago y confirma anticipos mediante `ERPBridge`.
- `migrations/m000_base_schema.py` y el servicio existente contemplan `links_pago`; la intención de venta pendiente se asegura desde `SalesService`.
- Hay pruebas de confirmación de webhook y de reservas/confirmación de venta pendiente, pero no cubren toda la superficie de seguridad y conciliación.

## 3. Hallazgos y riesgos priorizados

### P0 — Bloqueantes antes de producción

1. **Dos implementaciones de Checkout.** ERP y WhatsApp construyen preferencias por separado. Pueden divergir en referencias, montos, moneda, expiraciones, metadatos, idempotencia y persistencia. Consolidar la creación de intentos en una sola capa de aplicación/proveedor.
2. **Webhook de WhatsApp sin verificación de firma.** `whatsapp_service/webhook/mercadopago.py` no valida `x-signature` y `x-request-id`. Consultar el pago por ID no sustituye la autenticación de la notificación.
3. **Asociación ambigua de pagos WA.** `pago_flow.py` actualmente construye `external_reference` como `venta_id:phone` cuando `last_venta_id` existe, pero cae al teléfono si no lo tiene. El webhook intenta extraer el prefijo numérico y después hace fallback a la venta `pendiente_wa` más reciente por teléfono. Ese fallback sigue siendo ambiguo, y el formato `venta_id:phone` filtra un dato personal innecesario al proveedor. La referencia externa debe ser un identificador opaco, único e inmutable del intento de pago, relacionado en BD con un pedido/venta concretos.
4. **Idempotencia de negocio incorrecta y carrera de confirmación.** La clave `confirm_payment:{venta_id}:{monto}` no incluye `payment_id`; dos pagos legítimos del mismo importe podrían colisionar. Además, `SalesService.confirm_pending_payment_sale` consulta estado `pendiente_pago`, ejecuta la venta y después actualiza a `confirmada`; dos webhooks concurrentes pueden leer el mismo estado antes del commit. La deduplicación debe basarse en el ID único del pago del proveedor y proteger atómicamente el efecto de negocio con transacción/constraint.
5. **Monto y contexto no validados de extremo a extremo.** Antes de contabilizar, verificar estado `approved`, moneda esperada (MXN), monto exacto del intento, referencia, cuenta/receptor cuando esté disponible, pedido/venta asociados y que el intento admita ese pago. No confiar en monto ni teléfono del payload entrante.
6. **Respuesta del webhook y fallos.** El endpoint WA registra excepciones y devuelve `status=ok` incluso cuando falla el procesamiento; esto puede impedir reintentos y ocultar pagos no aplicados. Persistir notificación/estado de procesamiento y devolver respuesta que permita reintento ante fallo transitorio.

### P1 — Necesario para completar ambos canales

7. **Anticipo y liquidación no están unificados en el flujo WA inspeccionado.** `PagoFlow._handle_metodo` trata `pago_link` y llama a `_generar_link_pago(ctx)`, que usa `ctx.total_pedido()` como importe total, no el anticipo configurable. `ERPBridge` sí expone `registrar_anticipo` y `confirmar_pago_anticipo`, pero el creador de preferencias de `PagoFlow` no registra allí el intento ni vincula el ID de preferencia a un anticipo concreto. Falta un ledger de varios pagos por pedido, saldo restante, pagos parciales, devoluciones y conciliación.
8. **`links_pago` es demasiado estrecha como registro canónico.** Su clave `pedido_id` y campos actuales no representan bien varios pagos por pedido, varios intentos, canal (POS/WA), dispositivo Point, tipo de cobro (total/anticipo/liquidación), moneda, vencimiento, estados de procesamiento ni auditoría de notificaciones.
9. **El `X-Idempotency-Key` de proveedor se genera al vuelo.** Para creación/reintento de la misma operación se necesita una clave persistida y estable por intento; un intento nuevo debe tener una clave nueva.
10. **Contabilidad y comisión.** La documentación financiera describe que el ingreso MP se registra al confirmar webhook y menciona una comisión estimada fija del 3.6%. No se debe asumir esa tasa como comisión real: registrar importes/comisiones netos y brutos según datos reales de liquidación/operación y parametrización contable. Evitar duplicar el asiento al reintentar webhook.
11. **Point físico no está implementado en el código revisado.** No se encontró integración de dispositivo, emparejamiento, terminal_id, estado de orden Point ni reconciliación de cobro en terminal. La selección “terminal física” requiere definir modelo de Point, conectividad y API/SDK habilitado para la cuenta en México. No simular una terminal con un link.
12. **QR presencial debe distinguirse de Checkout link.** El QR mostrado en el POS puede ser un QR dinámico de cobro presencial, no necesariamente la misma URL de Checkout Pro convertida a imagen. Se debe elegir e implementar el producto/API QR compatible con la cuenta y sucursal, guardar el identificador/orden del QR y consultar el resultado en el mismo ciclo de pagos. Validar disponibilidad y requisitos en la cuenta real antes de comprometer endpoints.

## 4. Diseño objetivo recomendado

### 4.1 Una sola capa de dominio y un adaptador de proveedor

Mantener el estilo de inyección de dependencias existente:

- `PaymentApplicationService`: crea intentos, aplica políticas de anticipo/saldo, registra pagos, verifica consistencia y coordina la confirmación de ventas/pedidos.
- `MercadoPagoService`: adaptador HTTP del proveedor (Checkout/QR/Point), consulta de pagos/órdenes, cancelaciones/devoluciones soportadas y validación criptográfica de webhooks.
- Repositorios de pagos: persistencia de intentos, transacciones del proveedor, notificaciones y asignación a pedido/venta.
- POS y WhatsApp solo invocan casos de uso; no construyen payloads HTTP ni interpretan notificaciones por su cuenta.
- Conservar `SalesService` como autoridad de venta definitiva, inventario reservado y liberación de reserva. La aprobación de pago no debe crear una segunda ruta de venta.

El webhook público debe tener **una sola ruta canónica** y un procesador idempotente compartido. La app de escritorio no debe depender de que una computadora de mostrador exponga un puerto público. El microservicio desplegado puede actuar como ingress, pero debe llamar al mismo caso de uso/repositorio de pagos del ERP; evitar dos receptores activos que procesen la misma notificación en paralelo.

### 4.2 Modelo persistente propuesto

Añadir migración aditiva (no reemplazar tablas existentes):

- `payment_intents`: `id` UUID/ID estable, `order_type`, `order_id`, `sale_folio`, `channel` (pos/whatsapp), `method` (checkout/qr/point), `purpose` (total/anticipo/liquidacion), `amount`, `currency`, `provider`, `provider_reference`, `provider_order_id`, `provider_preference_id`, `idempotency_key`, `status`, `expires_at`, timestamps.
- `payment_transactions`: ID local, `intent_id`, `provider_payment_id` único, `amount`, `currency`, `status`, `status_detail`, `payment_method_id`, `fee/net` cuando la API lo informe, timestamps y payload normalizado.
- `payment_webhook_events`: ID/evento del proveedor, `request_id`, `signature_valid`, `payload_hash`, `processing_status`, `attempts`, error y timestamps. No guardar secretos ni datos de tarjeta.
- Índices únicos para `provider_payment_id`, referencia externa y clave de idempotencia; índices por pedido/venta y estado.

Compatibilidad: mantener y sincronizar `links_pago` como proyección legacy durante transición; no hacer `INSERT OR REPLACE` que pueda borrar un payment_id previo. La migración debe respetar los IDs UUIDv7/TEXT ya usados por el ERP.

### 4.3 Ciclo de vida único

1. Crear intención local pendiente con monto, canal, pedido/venta, propósito, moneda y clave idempotente persistida.
2. Crear el recurso de proveedor con referencia externa igual al ID de intención (nunca el teléfono). Guardar IDs/URLs/QR/terminal resultante.
3. Presentar al usuario QR/link o iniciar cobro en Point.
4. Recibir notificación autenticada; persistirla primero y responder rápido.
5. Consultar estado real del recurso en API de Mercado Pago.
6. Validar referencia, importe, moneda, receptor/cuenta y estado. Aplicar transacción local con bloqueo/unique constraints.
7. Aplicar el efecto de negocio una sola vez: confirmar venta POS mediante `SalesService.confirm_pending_payment_sale`; o registrar el anticipo/liquidación al pedido WA mediante un caso de uso que calcule saldo y no localice por teléfono.
8. Emitir eventos de dominio después del commit y notificar al cliente solo después de la aplicación correcta.
9. Conciliar periódicamente intentos pendientes/errores y permitir reintentos seguros.

Estados internos sugeridos: `created`, `pending`, `approved`, `rejected`, `cancelled`, `expired`, `refunded`, `review_required`, `processing_error`. Separar estado del intento de estado de la venta/pedido.

### 4.4 POS: QR + Point

- **QR:** generar QR dinámico ligado a la intención/venta exacta; mostrar importe, folio y estado pendiente en pantalla. No cerrar venta ni descontar inventario definitivamente hasta confirmación verificada.
- **Point:** crear orden/cobro en el dispositivo compatible, con terminal/dispositivo configurado por sucursal; mostrar “esperando tarjeta”, aprobado/rechazado/cancelado y reconciliar por identificador de orden/pago. No tratarlo como tarjeta manual ni link.
- Si no hay dispositivo/API autorizado o terminal emparejada, deshabilitar Point y ofrecer QR como alternativa explícita; no marcar pago como aprobado por acción manual.
- La documentación/API exacta de Point y QR debe verificarse con el modelo físico y credenciales de la cuenta de JUANIS/SPJ antes de implementar el adaptador. El código auditado no prueba compatibilidad con un modelo concreto.

### 4.5 WhatsApp: política por pedido

Persistir configuración por pedido (hoy no aparece conectada al método `pago_link` del `PagoFlow` inspeccionado):
- `payment_policy`: `full` o `deposit_then_balance`.
- `deposit_amount` o `deposit_percent` (validar que sea >0 y < total).
- `balance_due`, `paid_amount`, `payment_status`.

Para `full`, crear un intento por el total. Para `deposit_then_balance`, crear un intento por anticipo y, tras confirmación, actualizar el saldo; al preparar/entregar, crear un nuevo intento por el saldo restante. Cada anticipo/liquidación es un payment intent independiente. Rechazar sobrepagos salvo política explícita y soportada. Notificar folio, importe recibido y saldo pendiente.

## 5. Plan de implementación por fases

1. **Seguridad y modelo (P0):** migración aditiva, repositorios, firma de webhook, validación del pago, claves estables, deduplicación por payment_id, registro de eventos y reconciliación.
2. **Unificación Checkout (P0):** adaptar ERP y WhatsApp para invocar el mismo servicio; mantener temporalmente los métodos públicos legacy como fachadas.
3. **POS QR (P1):** adapter QR dinámico, UI de cobro, expiración/cancelación, confirmación por webhook y pruebas.
4. **WhatsApp total/anticipo/saldo (P1):** configuración por pedido, pagos múltiples, saldo y notificaciones; eliminar lookup por teléfono.
5. **Point físico (P1, condicionado):** identificar modelo/dispositivo y habilitación de cuenta, luego adapter Point por sucursal, polling/notifications y pruebas de estados.
6. **Contabilidad y conciliación (P1):** ledger de bruto/comisión/neto, depósitos y reembolsos según datos del proveedor, reportes de conciliación.
7. **Retiro gradual legacy:** desactivar webhook HTTP del escritorio y creadores de preferencias duplicados después de verificar tráfico, pruebas y rollback.

## 6. Pruebas obligatorias antes de habilitar producción

- Firma válida/inválida, replay, request_id, payload malformado y notificación duplicada.
- Mismo payment_id procesado dos o más veces produce un único efecto; dos payment_id diferentes del mismo importe se contabilizan como dos pagos solo si el saldo lo permite.
- Monto distinto, moneda distinta, referencia desconocida, pago pendiente/rechazado/cancelado y payment_id ajeno no confirman.
- Dos pedidos del mismo teléfono, dos anticipos iguales, pago tardío y pagos concurrentes no se cruzan.
- Pago total, anticipo, saldo, sobrepago, cancelación, expiración y devolución.
- POS QR y Point: aprobado, rechazado, timeout, cancelación desde terminal, desconexión y webhook tardío.
- Reserva de inventario se confirma/libera exactamente una vez; venta definitiva se crea una sola vez.
- Caja/tesorería/contabilidad registran un solo movimiento por transacción; no se registra ingreso al crear link.
- Pruebas de regresión para efectivo, tarjeta no integrada, pago mixto, WhatsApp y cierres de caja.

## 7. Decisiones y datos externos necesarios

Antes de activar Point real, confirmar el modelo exacto (Point Smart/Smart 2/Pro u otro), si cada sucursal tendrá terminal propia y que la cuenta Mercado Pago tenga habilitado el producto/API correspondiente. También se necesitan credenciales de prueba y URL HTTPS pública para webhook; nunca compartir tokens en el repositorio o chat. La integración debe comenzar en sandbox y pasar a producción después de pruebas de conciliación.

## 8. Archivos principales involucrados

- `pos_spj_v13.4/services/mercado_pago_service.py`
- `pos_spj_v13.4/core/services/sales_service.py`
- `pos_spj_v13.4/modulos/ventas.py`
- `pos_spj_v13.4/core/app_container.py`
- `pos_spj_v13.4/migrations/`
- `whatsapp_service/flows/pago_flow.py`
- `whatsapp_service/webhook/mercadopago.py`
- `whatsapp_service/erp/bridge.py` y los casos de uso/eventos de anticipos
- `pos_spj_v13.4/tests/test_mercado_pago_*.py` y nuevos tests de pagos/QR/Point

---
**Estado de esta rama:** auditoría/plan documentado. Sin cambios en lógica de producción, sin credenciales, sin despliegue y sin ejecución de pruebas.