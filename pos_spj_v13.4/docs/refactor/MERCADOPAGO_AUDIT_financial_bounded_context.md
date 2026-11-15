# Auditoría Mercado Pago sobre la rama financiera bounded context

**Rama auditada:** `claude/erp-financial-bounded-context-uqxz6b`  
**Fecha:** 2026-11-15  
**Alcance:** revisión estática de la arquitectura financiera/ventas, pagos del POS, puente y flujo de WhatsApp. No se ejecutó la suite completa ni se hicieron cobros reales.

## 1. Corrección de alcance

Esta auditoría se realiza sobre la rama indicada, no sobre `main`. La rama está fuertemente divergida de `main` (587 commits por delante y 57 por detrás en la comparación consultada), por lo que no es correcto trasladar automáticamente hallazgos o rutas de la rama principal. En particular, los archivos legacy `core/services/sales_service.py`, `modulos/ventas.py` y `services/mercado_pago_service.py` que se habían usado como referencia en una revisión anterior no se encontraron en las rutas consultadas de esta rama.

La arquitectura activa del POS está organizada en `backend/domain`, `backend/application`, `backend/infrastructure` y `frontend/desktop`. Las reglas de `CLAUDE.md` exigen preservar lógica de negocio, usar casos de uso/repositorios y no introducir SQL ni reglas financieras en UI.

## 2. Hallazgos confirmados en esta rama

### H1 — El dominio de Ventas ya modela Mercado Pago como medio de pago, no como integración del proveedor

`backend/application/sales/use_cases/payment_use_cases.py` contiene `RecordSalePaymentUseCase`. Su documentación indica explícitamente que Mercado Pago no se integra en ese caso de uso: el caso de uso registra un pago MP ya confirmado, con método `MERCADO_PAGO` y referencia igual al ID de pago del proveedor. Esto es correcto como separación de responsabilidades, pero deja fuera de ese contexto la creación de checkout, QR, Point, webhook y conciliación del proveedor.

**Implicación:** no introducir llamadas HTTP de Mercado Pago dentro de `RecordSalePaymentUseCase` ni dentro del agregado `Sale`. Crear una capa de aplicación de pagos/procesador que coordine el proveedor y después invoque los casos de uso existentes.

### H2 — El POS nuevo tiene un ciclo de cobro transaccional bien delimitado

`backend/application/sales/use_cases/checkout_use_cases.py` implementa `CheckoutSaleUseCase`. Exige que los pagos registrados cubran el total, confirma reserva de inventario, completa la venta, encola `PAYMENT_CONFIRMED` y `COMPLETED` en `sales_outbox` dentro de la transacción y compone efectos de Caja. La finalización es una única ruta oficial.

**Implicación:** el webhook de MP no debe marcar la venta COMPLETED por SQL ni duplicar inventario/caja/folio. Debe registrar el pago confirmado mediante `RecordSalePaymentUseCase`; cuando el saldo esté cubierto, ejecutar `CheckoutSaleUseCase` con permisos/contexto de sistema explícitos y operación idempotente.

### H3 — Las referencias de pagos de procesadores ya tienen política y unicidad

`backend/domain/sales/policies/payment_policy.py` exige referencia para CARD, TRANSFER y MERCADO_PAGO; limita formato a 4–64 caracteres y evita que un pago no-efectivo exceda el saldo pendiente. `payment_use_cases.py` consulta referencias ya usadas y `SaleRepository` aplica la protección de persistencia.

**Implicación:** persistir el `payment_id` real de Mercado Pago en `sale_payments.reference`. No usar el teléfono, folio ni un identificador generado localmente como sustituto de la referencia del proveedor. La clave local del intento de cobro debe ser distinta del payment_id.

### H4 — Finanzas recibe liquidaciones por el evento de venta completada

`backend/application/sales/integrations/finance_translator.py` traduce el método `MERCADO_PAGO` a `PAYMENT_PROCESSOR`. Puede conservar referencias por operación de procesador cuando el evento trae `payment_references`; el traductor agrega importes y referencias al contrato de Finanzas.

**Implicación:** el pago de MP debe entrar al agregado de Ventas y al payload de `SALE_COMPLETED` con referencia real, importe y moneda. No crear asientos o movimientos de tesorería directamente desde el webhook de proveedor, pues se duplicaría el flujo financiero de Ventas → Finanzas.

### H5 — El webhook de WhatsApp ya incorpora controles de seguridad importantes

`whatsapp_service/webhook/mercadopago.py`:
- limita el tamaño del cuerpo;
- valida `x-signature` y `x-request-id` mediante `verify_mp_signature`;
- aplica ventana anti-replay configurable;
- falla cerrado si falta secreto, salvo opt-in explícito sólo en desarrollo;
- acepta `payment.created` y `payment.updated`;
- consulta el pago real a `GET /v1/payments/{id}`;
- exige estado `approved`;
- valida moneda MXN y monto contra la venta;
- usa idempotencia por `mp_payment:{payment_id}`;
- deja pagos sin asignar en `whatsapp_unmatched_payments` y devuelve errores reintentables ante fallos transitorios.

**Implicación:** no reescribir esta seguridad desde cero. Reutilizar/extraer la validación de firma, consulta autoritativa, normalización de eventos y bandeja de excepciones para el procesador común.

### H6 — El webhook WA aún está acoplado al modelo legacy de anticipos/ventas

El webhook usa `external_reference = venta_id:phone`, consulta la tabla legacy `ventas` y espera estado `pendiente_wa`. Después llama a `ERPBridge.confirmar_pago_anticipo`. La función legacy busca el primer anticipo pendiente por `venta_id` y actualiza `ventas.estado/anticipo_pagado`. El match comprueba el teléfono y compara el importe con el total de la venta, por lo que el flujo real inspeccionado representa el pago total de esa venta, no un ledger de múltiples intentos parciales.

**Riesgo:** aunque ya no hay fallback al pedido más reciente por teléfono, el acoplamiento a `venta_id:phone` y al primer anticipo pendiente no soporta de forma robusta varios anticipos, varios intentos o liquidaciones parciales sobre el mismo pedido.

### H7 — El flujo conversacional WA todavía crea la preferencia directamente

`whatsapp_service/flows/pago_flow.py` llama directamente a `POST /checkout/preferences`, calcula el importe con `ctx.total_pedido()`, forma `external_reference` como `venta_id:phone` (o sólo teléfono si no hay venta) y no usa el caso de uso nuevo de Ventas ni el modelo de referencia de pago de la nueva arquitectura. No se ve persistencia de un intento de proveedor en el flujo de creación de preferencia.

**Riesgo:** el canal WhatsApp puede divergir del POS en importe, idempotencia, expiración, estado, conciliación y referencia. Tampoco implementa la política solicitada de pago total o anticipo + saldo según el pedido.

### H8 — El ERP Bridge conserva un PaymentGateway orientado a anticipos legacy

`whatsapp_service/erp/bridge.py` expone `register_advance` y `confirm_payment`; su implementación SQLite registra un anticipo pendiente y confirma el primer anticipo pendiente por venta. Es una interfaz de compatibilidad útil para pedidos WA actuales, pero no debe convertirse en el nuevo servicio central de pagos del ERP ni recibir lógica Point/QR.

### H9 — El modelo financiero del branch debe seguir siendo la autoridad contable

`docs/architecture/FINANCIAL_TRACEABILITY_END_TO_END.md` establece la cadena de evento origen, documento financiero, movimiento de tesorería, asiento contable, bitácora y conciliación. El `finance_translator` ya conecta `SALE_COMPLETED` con Finanzas.

**Implicación:** MP debe producir evidencia y referencias de cobro, no contabilizar por una ruta paralela. Las comisiones y netos del procesador requieren conciliación con información real del proveedor; no asumir una tasa fija.

## 3. Arquitectura recomendada respetando el bounded context

No crear un segundo sistema de ventas ni meter Mercado Pago en el agregado `Sale`. Introducir un bounded context/capa de Payments con estos límites:

1. **Payments domain:** `PaymentIntent`, `ProviderPayment`, `PaymentAllocation`, políticas de importe/saldo/moneda y estados del intento.
2. **Payments application:** casos de uso `CreatePaymentIntent`, `StartCheckout`, `StartQrPayment`, `StartPointPayment`, `HandleProviderNotification`, `ReconcilePayment`, `RefundPayment` (si la API y reglas de negocio lo permiten).
3. **Payments infrastructure:** adaptador Mercado Pago para Checkout Pro, QR presencial y Point; repositorios; firma webhook; cliente HTTP; almacenamiento de eventos y consultas.
4. **Integración con Ventas:** al confirmar proveedor, llamar `RecordSalePaymentUseCase` con `method=MERCADO_PAGO`, importe y payment_id. Si la venta ya está completamente pagada, invocar la ruta oficial `CheckoutSaleUseCase`. Mantener el flujo de pagos mixtos y la política de saldo.
5. **Integración con Finanzas:** sólo por `SALE_COMPLETED` y `finance_translator`; conciliación de comisiones por su caso de uso/ledger financiero, con operation_id idempotente.
6. **Integración WhatsApp:** el microservicio llama al API/caso de uso de Payments; nunca crea preferencias directamente ni decide qué venta confirmar con un SELECT por teléfono.

## 4. Persistencia propuesta (aditiva)

Antes de agregar tablas, revisar las migraciones activas del bounded context financiero y las tablas ya disponibles para no duplicar ledger. Si no existe equivalente, agregar migración para:

- `payment_intents`: UUIDv7, venta/pedido, canal POS/WhatsApp, método Checkout/QR/Point, propósito total/anticipo/liquidación, importe Decimal, moneda, clave idempotente local, referencia externa opaca, estado, expiración y timestamps.
- `provider_payment_transactions`: proveedor, payment_id UNIQUE, intent_id, importe, moneda, estado, status_detail, fee/net cuando se obtenga y referencia de operación.
- `provider_webhook_events`: request_id, payment_id, hash del payload, firma válida, estado de procesamiento, intentos, error y timestamps.
- `payment_allocations` si se requiere separar varios pagos de un pedido/venta, anticipo y saldo sin sobreescribir registros anteriores.

Mantener `links_pago`/anticipos legacy como compatibilidad mientras se migra; no reutilizar una tabla con clave natural por pedido como único ledger si un pedido puede recibir varios cobros.

## 5. Flujos funcionales solicitados

### POS
- QR dinámico: crear intent local por venta e importe pendiente, generar QR asociado a esa intent, mostrar estado en UI; webhook/polling consulta el proveedor; sólo entonces registrar payment y completar por los casos de uso oficiales.
- Point físico: seleccionar terminal configurada por sucursal, crear orden de terminal, rastrear estados y payment_id, manejar cancelación/timeout/rechazo. No simular Point con Checkout URL.

### WhatsApp
- Política por pedido `FULL` o `DEPOSIT_THEN_BALANCE`.
- FULL: intent por el saldo total.
- DEPOSIT_THEN_BALANCE: intent por anticipo; tras confirmación, guardar pago asignado y saldo pendiente; crear intent independiente por saldo cuando corresponda.
- Cada cobro tiene referencia externa opaca y única; no incluir teléfono en external_reference.
- Mensajes de WhatsApp informan importe pagado y saldo actualizado sólo después del commit del ERP.

## 6. Plan de trabajo seguro

1. Inventario final de rutas y contratos activos de Payments, Ventas, Finanzas y WA en esta rama; localizar y probar la implementación legacy de Checkout que el código documenta pero que no aparece en las rutas antiguas revisadas.
2. Diseñar el contrato Payments ↔ Sales y el mecanismo de autorización de sistema para webhooks, sin saltarse permisos de UI en llamadas interactivas.
3. Añadir esquema aditivo y repositorios con UUIDv7, claves únicas e idempotencia.
4. Extraer seguridad/consulta MP del webhook WA a adaptador compartido y conservar el endpoint como fachada.
5. Implementar Checkout Pro común y migrar WhatsApp; mantener feature flag y compatibilidad.
6. Implementar QR presencial POS.
7. Implementar Point cuando se confirme modelo de terminal y habilitación API de la cuenta.
8. Incorporar pagos parciales por pedido WA, conciliación y reportes.
9. Agregar pruebas de contrato, concurrencia, firma, replay, pago duplicado, monto/moneda incorrectos, pago tardío, cancelación, refund, dos pedidos del mismo teléfono y regresión de caja/inventario/finanzas.

## 7. Estado

Esta es una auditoría estática focalizada sobre la rama especificada y los archivos enumerados. No se ejecutó la suite de pruebas, no se probaron credenciales ni terminales reales y no se modificó código productivo. El siguiente paso de implementación debe comenzar por inventariar las rutas activas del adaptador Mercado Pago legacy y el composition root de esta rama, para no crear duplicados ni romper los límites del bounded context.


## 9. Avance posterior a la auditoría — fundación Payments

Por aprobación del responsable, se inició la implementación siguiendo los límites recomendados:
- Nuevo dominio puro `backend/domain/payments` con `PaymentIntent`, enums y excepciones.
- Referencia externa opaca UUIDv7; validación de importe Decimal, moneda y referencia; replay idempotente sólo para el mismo payment_id y después de revalidar el contenido.
- Pruebas unitarias de dominio en `tests/unit/domain/payments/test_payment_intent.py`.
- Documento de límites y fases en `docs/architecture/PAYMENTS_BOUNDED_CONTEXT.md`.
- Registro del avance en `migrations/MIGRATION_LOG.md`.

Esta entrega **no** incluye aún persistencia, API de Mercado Pago, webhooks compartidos, QR, Point, WhatsApp parcial ni integración UI. Tampoco se ejecutaron localmente las pruebas; el código debe pasar CI y revisión antes de avanzar a la fase de infraestructura.
