# ORD-26 — Notificaciones: Customer / Internal / WhatsApp / Policies

Fecha: 2026-09-01. Alcance: master prompt ORD-26 ("1. Customer. 2. Internal. 3. WhatsApp.
4. Policies. 5. Tests."). Extiende ORD-23 (que solo cubría aprobación pendiente y listo
para recoger) con más disparadores del ciclo de vida de entrega, agrega el canal
"Internal" (alertas a staff) que no existía, y centraliza la decisión "qué evento
necesita qué notificación" en una política única en vez de si/else repetidos.

## Qué se construyó

- **Policies**: `backend/domain/orders_delivery/policies/notification_policy.py` —
  `DeliveryNotificationPolicy.customer_message(event_name, **context)` (plantilla de
  texto para el cliente, o `None` si el evento no aplica) y
  `.requires_internal_alert(event_name)` (bool). Deliberadamente NO es un motor de
  reglas configurable en base de datos como CASH-20 (`cash_alert_rules`/
  `cash_notification_jobs`, su propio esquema+dispatcher) — construir esa infraestructura
  completa para un segundo bounded context excede el alcance de esta fase; esto es una
  política pura y estática, totalmente probable, con la puerta abierta a una versión
  configurable por sucursal si el negocio la pide después.
- **Customer** (extiende ORD-23): `DeliveryNotificationPolicy` agrega mensajes para
  `DELIVERY_DISPATCHED` ("va en camino"), `DELIVERY_COMPLETED` ("fue entregado"),
  `DELIVERY_FAILED` ("no pudimos entregar"), cableados como efecto colateral best-effort
  en `DispatchDeliveryJobUseCase` y `RecordDeliveryAttemptUseCase` (éxito Y falla).
- **Internal** (nuevo): `backend/infrastructure/integrations/
  orders_delivery_internal_notifier.py` — `OrdersDeliveryInternalNotifier.notify_roles()`
  escribe en la tabla CANÓNICA `notification_inbox` (`migrations/m000_base_schema.py`,
  la misma bandeja que ya lee el escritorio del ERP), resolviendo destinatarios por rol
  vía `usuarios`/`usuarios_roles`/`roles` — mismo criterio de resolución de roles que
  `whatsapp_service/erp/pos_notifier.py` ya usa del lado del microservicio (adaptado aquí
  al backend con identidades UUIDv7, no las legacy). Se activa en `RecordDeliveryAttemptUseCase`
  cuando la entrega falla, alertando a `admin`/`gerente` de la sucursal.
- **WhatsApp**: `OrdersDeliveryWhatsAppClient` gana `send_message()`, un método
  genuinamente genérico — antes de esta fase, el único método de texto libre
  (`notify_customer_approval_required`) tenía la redacción fija a "requiere tu
  aprobación", que habría sido incorrecta para "tu pedido va en camino"/"fue entregado".

## Decisión notable: NO reusar `pos_notifier.py::_ensure_notification_inbox()`

Ese helper (lado microservicio WhatsApp) define columnas extra (`dedupe_key`, `severity`)
que el esquema canónico de `m000_base_schema.py` NO tiene — como la tabla ya existe para
cuando ese código corre, su propio `CREATE TABLE IF NOT EXISTS` es un no-op silencioso y
esas columnas nunca se crean realmente. Es un bug real, latente, en ese módulo — pero
pertenece a un proceso separado (microservicio WhatsApp) y queda fuera de alcance
corregirlo aquí; `OrdersDeliveryInternalNotifier` simplemente nunca escribe esas dos
columnas, evitando heredar el problema.

## Efecto colateral encontrado y corregido (mismo patrón que ORD-23)

Cablear notificaciones automáticas dentro de `DispatchDeliveryJobUseCase`/
`RecordDeliveryAttemptUseCase` (ya probados desde ORD-18/19) hizo que sus pruebas
existentes, sin ningún `whatsapp_client` inyectado, empezaran a intentar red real de
nuevo (mismo síntoma que ORD-23 ya documentó). Corregido inyectando `_NoOpWhatsAppClient`
en los 2 archivos de prueba afectados
(`test_orders_delivery_dispatch_use_cases.py`, `test_orders_delivery_redelivery_use_cases.py`).

## Tests

13 tests nuevos: 7 unitarios de `DeliveryNotificationPolicy`, 3 de
`OrdersDeliveryInternalNotifier` (incluye el caso "sin tablas `usuarios`, nunca falla") y
3 de la integración completa despachar→notificar cliente / fallar→notificar cliente Y
alertar admin, contra el esquema canónico completo (`tests/integration/_born_clean_db.py`)
capado con los esquemas de `orders_delivery`/`inventory`. Suite combinada
`orders_delivery` + `logistics`: **394/394 pasando**.

## Pendiente

- Política configurable por sucursal/severidad (ver "Policies" arriba) — decisión de
  negocio pendiente, no una omisión técnica.
- Plantillas de mensaje para más eventos (`REDELIVERY_REQUESTED`, `RETURNED_TO_BRANCH`) —
  se dejaron fuera por alcance, la tabla de plantillas es trivial de extender cuando se
  pida.
- ORD-27 (Analytics: KPI/Charts/SLA/Driver performance) — siguiente en la instrucción del
  usuario "ORD-25 hasta ORD-30".
