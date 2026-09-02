# ORD-22 — Ventas y Finanzas

Fecha: 2026-08-31. Alcance: master prompt §22 (proyección de `CustomerOrder` a `Sale`,
estado de pago, Caja, reembolso). Primera fase que cruza de "core delivery" (ORD-1..21,
ahora cerrado) hacia la integración con Ventas/Finanzas.

## Qué se construyó

- `PaymentStatus` (§15, 8 estados) ya existía desde ORD-2 sin ningún caso de uso que lo
  mutara. `OrderPaymentPolicy` (nueva) — tabla de transiciones + `resolve_from_amounts()`
  (una sola función de decisión, mismo patrón que ORD-20/21 usaron para cobro/liquidación).
- `CustomerOrder.link_sale()`/`apply_payment_status()` (nuevos métodos, idempotentes:
  re-vincular la MISMA venta o reaplicar el MISMO estado es no-op; vincular una venta
  DISTINTA o una transición inválida lanza). `CustomerOrderLine.billable_quantity()`/
  `billable_unit()` — exponen públicamente la prioridad peso-si-catch-weight-si-no
  cantidad que `final_subtotal` ya usaba internamente, porque `AddSaleLineUseCase`
  necesita una cantidad real, no un subtotal derivado.
- `OrdersDeliverySalesClient` (`backend/infrastructure/integrations/`) — envuelve las
  casos de uso REALES de Ventas (`StartSaleUseCase`/`AddSaleLineUseCase`/
  `BeginSaleCheckoutUseCase`/`RecordSalePaymentUseCase`/`CheckoutSaleUseCase`/
  `ReverseSaleUseCase`), mismo principio "Pedidos no escribe" que ORD-8 estableció para
  Inventario. `CheckoutSaleUseCase` (no el más simple `CompleteSaleUseCase`) porque ya
  trae los efectos reales de Caja (`SalesCashEffectsClient`) — la mitad "Caja" de este
  alcance no se reimplementa, ya vive dentro de Ventas.
- 3 casos de uso nuevos (`backend/application/orders_delivery/use_cases/
  sales_finance_use_cases.py`): `ProjectOrderToSaleUseCase`, `RecordOrderPaymentUseCase`,
  `ReverseCustomerOrderUseCase`. Los tres reutilizan permisos existentes
  (`ORDER_CONFIRM`/`ORDER_REVERSE`) — el catálogo §63 de este bounded context no tiene un
  grupo de "finanzas" propio; el lado del dinero lo revalida Ventas con sus propios
  permisos (`SalesAuthorizationPolicy`), igual que ORD-8 dejó que Inventario revalidara
  los suyos.

## Decisiones

- **Autorización de Ventas NO tiene default permisivo, a propósito.** A diferencia de
  `OrdersDeliveryInventoryClient` (ORD-8), que confía silenciosamente en que las casos de
  uso de Inventario por defecto usan `permissive_for_tests()` (una brecha real, aún
  abierta, no cerrada por esta fase) — `_SalesBaseUseCase` falla cerrado explícitamente sin
  un `SalesAuthorizationPolicy` real (`SalesConfigurationError`, con su propio docstring:
  "an unconfigured authorization gate must never allow"). Se respetó ese endurecimiento en
  vez de rodearlo: `OrdersDeliverySalesClient` exige que el llamador inyecte una política
  real (producción) o `permissive_for_tests()` (pruebas) — nunca un default silencioso.
- **Un reembolso siempre reversa la venta COMPLETA** (`ReverseSaleUseCase`), nunca una
  `ReturnSaleLineUseCase` parcial — `CustomerOrder` no tiene su propio tracking de
  devoluciones por línea, así que no hay una forma correcta de mapear un reembolso
  parcial de pedido a líneas específicas de venta todavía.
- **`authorize_exception()` para el reembolso reutiliza exactamente el caso que su propio
  docstring (ORD-1) ya nombraba** ("reverso de entrega entregada, reembolso") — primera
  vez que se usa para esto, aunque ORD-10 ya lo había estrenado para peso fuera de
  tolerancia.
- **operation_id por paso SIEMPRE se genera fresco (`new_uuid()`), nunca por sufijo** —
  confirmado leyendo `backend/domain/sales/events.py::sale_event_payload()`: Ventas
  también exige UUIDv7 canónico en `operation_id`, igual que `orders_delivery`'s propios
  `order_event_payload()`/`delivery_event_payload()`. El patrón de ORD-8
  (`f"{operation_id}-{line.id}"`) solo es seguro contra Inventario porque
  `build_event_payload()` de Inventario NO valida formato — exactamente la misma clase de
  bug que ORD-21 encontró y corrigió, verificada aquí ANTES de escribir código en vez de
  después.

## Bugs encontrados y corregidos ANTES de completar la fase (no en producción)

1. **`AddSaleLineUseCase` no es idempotente** (a diferencia de `StartSaleUseCase`, que sí
   lo es por `operation_id`) — un reintento tras un fallo a mitad de proyección
   duplicaría líneas. Corregido: `project_order_to_sale()` solo agrega líneas cuando la
   Sale recién iniciada todavía no tiene ninguna.
2. **`RecordSalePaymentUseCase`/`Sale.reverse()` tampoco son idempotentes** — un
   reintento podría cobrar dos veces o fallar reversando una venta ya reversada.
   Corregido: `RecordOrderPaymentUseCase`/`ReverseCustomerOrderUseCase` consultan
   `orders_delivery_outbox.get_by_operation_id()` (nuevo método, §58's `UNIQUE
   (operation_id)`) ANTES de llamar a Ventas — si ya existe, la operación ya se completó
   y se responde con éxito sin repetir la llamada. La ventana angosta entre "Ventas ya
   confirmó" y "este módulo aún no confirmó" queda como límite arquitectónico aceptado y
   documentado (misma clase de límite que `CheckoutSaleUseCase` ya acepta para su propio
   efecto de Caja best-effort) — cerrarla del todo requeriría una saga/compensación que
   excede el alcance de esta fase.
3. **`Sale.record_payment()` exige estado `CHECKOUT_PENDING`/`PAYMENT_PENDING`, nunca
   `ACTIVE`** — una Sale recién proyectada se queda en `ACTIVE` tras agregar líneas.
   Corregido: `project_order_to_sale()` llama `BeginSaleCheckoutUseCase` una vez que las
   líneas están listas, también protegido contra reintento (solo si `sale.status ==
   "ACTIVE"`).

Los tres se encontraron escribiendo las pruebas de integración contra el pipeline real
(mismo método que ya atrapó los bugs de ORD-14/15/17/21), no en producción.

## No resuelto / decisión abierta

- **Efectivo contra entrega (`DriverCashCollection`/`DriverSettlement`, ORD-20/21) NO se
  unificó con pagos de Sale** — el efectivo cobrado por un repartidor se reconcilia contra
  el `DeliveryJob`, nunca se postea como línea de pago de Ventas. Unificarlos sería un
  cambio de alcance real; queda documentado como pregunta abierta, no decidido en
  silencio.
- Reembolso parcial por línea (mapear `ReturnSaleLineUseCase` a líneas específicas del
  pedido) — fuera de alcance, ver arriba.

## Tests

26 tests nuevos (15 unitarios de dominio + 11 de integración end-to-end contra
`orders_delivery` + `inventory` + `sales` en la misma conexión SQLite, incluyendo el
pipeline completo captura→confirmar→reservar→preparar→listo para recoger→PROYECTAR A
VENTA→PAGAR→completar recolección→REEMBOLSAR). Suite acumulada de `orders_delivery`:
**335/335 pasando**. Suite de Ventas verificada por separado sin regresiones (382/384; los
2 fallos restantes son de `test_sales_inventory_stock_consistency.py`, con identidades
enteras legacy, sin relación alguna con `orders_delivery` — confirmado no tocar ningún
archivo de esa ruta).

## Pendiente

- Continúa ORD-23 (según el master prompt: notificaciones/WhatsApp del cliente) y ORD-24
  (dispatcher del outbox transaccional) — el usuario autorizó explícitamente continuar
  ORD-13 hasta ORD-24.
