# SALES-16 — Cancelaciones y devoluciones (POS-16 del master prompt)

Fecha: 2026-08-17
Fase anterior: `SALES-15_suspensiones.md`.

## Alcance ejecutado

Master prompt §67, fase POS-16: "Cancel. Return. Reverse. Authorization. Tests."

"Cancel" ya existía (`Sale.cancel()`/`CancelSaleUseCase`, SALES-6) — pre-pago únicamente, una
venta COMPLETED debe reversarse, no cancelarse (§42, ya codificado en `SaleCancellationPolicy`
desde SALES-3). Esta fase construyó los tres huecos reales: Return, Reverse y Authorization.

## Investigación previa (agente de research, sin escritura de archivos)

Investigué `core/services/sales_reversal_service.py` (890 líneas) completo, la única
implementación real y funcionando de este dominio en el repositorio.

**Hallazgo clave — el legacy SÍ distingue tres operaciones, no solo cancelar**:
`cancel_sale` (cancelación total, restaura TODO el inventario, revierte puntos de fidelidad, sin
asiento contable), `refund_items` (devolución REAL de artículos parciales — tabla `sale_refunds`,
guarda contra sobre-devolución, restaura solo lo devuelto, sí postea asiento) y
`issue_credit_note` (ajuste puramente financiero, sin movimiento de inventario). Pero
**`refund_items` está completamente sin conectar** — cero llamadas desde cualquier UI o caso de
uso, confirmado por grep; el diálogo de Devolución de `modulos/ventas.py` no tiene ningún control
de selección de artículo/cantidad, solo puede cancelar la venta completa.

**Hallazgo clave — la restauración de inventario legacy ya usa la pila nueva**:
`_post_canonical_return`/`_restore_stock_canonical` no reinventan nada — postean un movimiento
`MovementType.SALE_RETURN` real vía `PostInventoryMovementUseCase` (el ledger canónico de
Inventory, `owns_transaction=False`, compone dentro de la transacción del llamador). Reutilicé
este patrón exacto (mismo `warehouse_id=branch_id`, mismo `InventoryStatus.AVAILABLE`) en vez de
inventar una ruta paralela.

**Hallazgo clave — cero autorización en caliente para devoluciones, en ningún lado**: el flujo
real de Devolución (`modulos/ventas.py::_cancelar`) solo re-verifica un permiso plano
(`core.permissions.verificar_permiso`, `"ventas.cancelar"` — un código DISTINTO al nuevo
`SalesPermissions.RETURN`/`REVERSE`) para el MISMO usuario ya autenticado — sin PIN, sin segundo
aprobador, nada parecido a autorización en caliente. La maquinaria real
(`SalesAuthorizationPolicy.authorize_exception`, activa desde SALES-2) solo se usaba para
descuentos hasta ahora — nunca para devolución/reversa. Esta fase cierra ese hueco para la pila
nueva, sin tocar el flujo legacy.

**Hallazgo clave — el legacy conflate "cancelar completada" y "reversar"**: no existe ningún
concepto legacy distinto de "reversa de una venta completada" — `cancel_sale` solo revisa
`estado == 'completada'` y pasa directo a `'cancelada'`. La pila nueva ya reservaba
`SaleStatus.REVERSED` como estado terminal distinto desde SALES-3 (con transición
`COMPLETED → REVERSED` ya válida) — esta fase por fin construye el método de dominio que lo usa.

## Entregables

### Dominio

- `backend/domain/sales/value_objects/sale_return.py::SaleReturn` — línea de devolución
  inmutable (id, sale_id, line_id, quantity, amount, reason, requested_by_user_id,
  authorized_by_user_id). El monto es proporcional: `(line.line_total / line.quantity) *
  quantity` — como `line_total` ya descuenta descuento/impuesto de esa línea, una devolución
  parcial de una línea con descuento reembolsa el precio con descuento, no el de lista.
- `backend/domain/sales/policies/return_policy.py::SaleReturnPolicy` — `ensure_can_return`
  (COMPLETED/RETURNED_PARTIALLY únicamente), `ensure_quantity_within_line` (guarda contra
  sobre-devolución, misma regla que `refund_items` legacy ya aplica), `ensure_can_reverse`
  (solo desde COMPLETED).
- `Sale.return_line()` — nunca muta la `SaleLine` original (sigue siendo el registro histórico de
  lo realmente vendido, misma razón por la que `product_snapshot` tampoco se muta); determina
  RETURNED_PARTIALLY vs RETURNED_FULLY comparando el total devuelto acumulado contra el total
  vendido. `Sale.reverse()` — transición directa COMPLETED→REVERSED, exige motivo no vacío.
- Tres excepciones nuevas: `SaleReturnNotAllowedError`, `ReturnQuantityExceededError`,
  `SaleReversalNotAllowedError`.
- Cero eventos nuevos — `SaleEvents.RETURNED`/`REVERSED` ya existían reservados desde SALES-3,
  nunca publicados hasta ahora.

### Esquema

`sale_returns` (mirrors `sale_payments`) + `sales.reversed_at` — migración 203.

### Infraestructura

- `SalesInventoryClient.restore_for_return()` — envuelve `PostInventoryMovementUseCase` con
  `MovementType.SALE_RETURN`, exactamente el patrón real que `sales_reversal_service.py` ya usa.
  A diferencia de `SalesCashEffectsClient` (SALES-14), **esta sí compone atómicamente**:
  `InventoryUnitOfWork` soporta `owns_transaction=False`, así que se une a la transacción de
  `SalesUnitOfWork` del llamador — la primera composición real de dos bounded contexts en una
  sola transacción, exactamente lo que `SalesUnitOfWork` documentaba como su propósito desde
  SALES-5.
- `SalesCashEffectsClient.reverse_completed_sale()` — conecta
  `CashSalesIntegrationService.reverse_sale_cash` (real, escribe una `CashLedgerEntry` tipo
  `REVERSAL`) — mismo efecto de mejor esfuerzo post-commit que SALES-14 ya estableció (Caja
  sigue sin soportar composición atómica).

### Aplicación

`backend/application/sales/use_cases/return_use_cases.py`:
- `ReturnSaleLineUseCase` — exige `SalesPermissions.RETURN` para el solicitante Y
  `authorize_exception` (autorizador DISTINTO, mismo permiso) antes de aplicar la devolución —
  **la autorización aquí NO es opcional** (a diferencia de los descuentos, donde solo los montos
  grandes la requieren) — decisión deliberada dado que el propio hallazgo de investigación
  confirma que este es exactamente el hueco de seguridad real que existe hoy. Restaura
  inventario real dentro de la misma transacción.
- `ReverseSaleUseCase` — misma exigencia de autorización en caliente. Restaura TODO el inventario
  de la venta (todas las líneas, cantidad completa) y, tras el commit, intenta revertir el efecto
  de caja (mejor esfuerzo, no bloqueante).

**Orden deliberado para atomicidad real**: en ambos casos, la mutación de dominio
(`return_line()`/`reverse()`) — barata, en memoria — corre primero. La restauración de
inventario (I/O real, compuesta con `owns_transaction=False`) corre después. A diferencia de
`StockReservationService` (SALES-9), que se protege sola con su propio SAVEPOINT,
`PostInventoryMovementUseCase` con `owns_transaction=False` NO se limpia sola ante un fallo —
depende de que el dueño de la transacción externa haga rollback. Por eso, si la restauración de
inventario falla DESPUÉS de que la mutación de dominio ya tuvo éxito, el caso de uso llama
`uow.rollback()` explícitamente antes de retornar el fallo, en vez de confiar en el
"retornar sin lanzar excepción = commit implícito" que las fases anteriores podían asumir con
seguridad porque su único I/O arriesgado corría ANTES de cualquier mutación.

**Permisos**: cero cambios en `permission_catalog.py` — `SalesPermissions.RETURN`
(`"POS.devolucion"`) y `REVERSE` (`"POS.reverso"`) ya existían desde SALES-2. El autorizador debe
sostener el MISMO permiso (no existe un permiso "override" separado para devolución/reversa,
a diferencia de descuentos que sí tienen `DISCOUNT_OVERRIDE`).

### Tests

19 nuevos en `tests/unit/test_sales_returns.py` (334 en total en la suite SALES-0..16, un solo
failure preexistente no relacionado ya documentado desde SALES-9), todos verdes en la primera
corrida: dominio (estado inválido rechazado, transición parcial→completa, segunda devolución
parcial que completa la línea, sobre-devolución rechazada, monto proporcional correcto, reversa
exige COMPLETED y motivo, no se puede reversar dos veces); casos de uso (exige permiso, exige
autorizador distinto — segregación de funciones real, verificada — restaura inventario REAL vía
el ledger canónico, verificado con `InventoryAvailabilityQueryService`, una sobre-cantidad falla
sin tocar inventario en absoluto, emite el evento correcto al outbox, reversa completa y
restaura todo el inventario, captura el error de efectos de caja sin bloquear la reversa).

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se conectó `issue_credit_note`** (ajuste puramente financiero) — el master prompt no lo
  nombra en la lista de esta fase (Cancel/Return/Reverse/Authorization), y no hay ningún
  precedente de UI para él tampoco.
- **No se posteó ningún asiento contable (GL) para devolución/reversa en la pila nueva.** La
  propia venta completada de la pila nueva nunca postea un asiento en primer lugar (confirmado
  desde SALES-6/13: `backend/application/sales` no está conectado a `PostingEngine` ni al
  `GeneralLedgerService` legacy) — reversar un asiento que nunca se posteó no aplica. Esto es
  consistente con el alcance ya establecido de toda esta pipeline, no un hueco nuevo de esta fase.
- **No se tocó `modulos/ventas.py`.** El diálogo de Devolución legacy sigue llamando
  `SalesReversalService.cancel_sale` directamente, sin selección de artículo/cantidad y sin
  autorización en caliente real — el propio hallazgo de esta fase, documentado, no corregido en
  el lado legacy.
- **No se resolvió el límite arquitectónico de Caja** (mismo hallazgo de SALES-14): la reversión
  del efecto de caja sigue siendo de mejor esfuerzo, no atómica con la propia venta.

## Siguiente fase

El master prompt continúa con POS-17 (Document Output) — confirmar alcance con el usuario antes
de asumir.
