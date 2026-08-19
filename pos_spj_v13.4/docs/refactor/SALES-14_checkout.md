# SALES-14 — Checkout (POS-14 del master prompt)

Fecha: 2026-08-17
Fase anterior: `SALES-13_pago.md`.

## Alcance ejecutado

Master prompt §67, fase POS-14: "Atomic operation. Outbox. Cash effects. Inventory. Loyalty.
Tests." Esta fase compone en UN solo caso de uso todo lo que las fases anteriores dejaron
construido pero suelto: pagos ya registrables (SALES-13), reserva de inventario ya reservable
pero nunca confirmada en ningún flujo real (SALES-9), y fidelidad que solo podía previsualizarse,
nunca canjearse de verdad (SALES-11).

## Investigación previa (sin escritura de archivos)

Antes de diseñar, leí directamente: `SalesUnitOfWork` (ya documentaba desde SALES-5 su propio
propósito exacto — "a real POS checkout will need to compose Sales + Inventory + Cash writes
inside one outer SAVEPOINT"), `ConfirmInventoryReservationUseCase` (SALES-9, nunca conectado a
ningún flujo), `CashSalesIntegrationService.record_completed_sale` (Caja, real y completo, pero
sin ningún handler que lo suscriba a un evento de Sales — confirmado en SALES-13), y
`LoyaltyService.canjear`/`apply_redemption` (canje REAL, distinto de `preview_redemption`).

**Hallazgo arquitectónico real, no anticipado**: `CashRegisterUnitOfWork` (a diferencia de
`SalesUnitOfWork`/`InventoryUnitOfWork`) no tiene bandera `owns_transaction` — su `__exit__`
siempre llama `connection.commit()` directamente. Esto significa que `record_completed_sale` NO
puede componerse dentro de la misma transacción atómica que completa la venta sin comprometer
(commit) esa transacción prematuramente. Es un límite real de la arquitectura actual de Caja, no
un descuido de esta fase — documentado explícitamente, no ocultado (ver "Cash effects" abajo).

**Hallazgo favorable, no anticipado**: `LoyaltyService.canjear`/`apply_redemption` SÍ está
diseñado para componerse en una transacción externa — su propio comentario dice "La transacción
la controla el orquestador superior (SalesService/SAVEPOINT)" y `_registrar_pasivo(commit=False)`
nunca hace commit por su cuenta. A diferencia de Caja, el canje de fidelidad SÍ puede — y se
compone — dentro de la misma transacción atómica de Sales.

## Entregables

### Atomic operation — `CheckoutSaleUseCase`

`backend/application/sales/use_cases/checkout_use_cases.py`. Un solo `SalesUnitOfWork` (verdadera
atomicidad, no solo en apariencia): el orden importa y está documentado en el propio código —
1. Validar (sin ningún I/O todavía) que la venta puede transicionar a COMPLETED
   (`SaleLifecyclePolicy.ensure_transition`) y que el pago está completo
   (`SalePaymentPolicy.ensure_fully_paid`, SALES-13). Si falla aquí, no se tocó nada — commit
   vacío, no-op seguro.
2. Solo si el paso 1 garantiza éxito, confirmar la reserva de inventario (I/O real vía
   `SalesInventoryClient.confirm`, SALES-9's `ConfirmInventoryReservationUseCase` finalmente
   conectado a un flujo real).
3. `sale.complete()` — re-valida (barato, garantizado a pasar dado el paso 1).
4. `uow.sales.save(sale)` + outbox.

Este orden evita el problema real de "el paso 2 tuvo éxito pero el paso 3 falla y ya no hay forma
limpia de revertir dentro del mismo `with`" — moviendo toda validación que puede fallar ANTES de
cualquier mutación de I/O, en vez de intentar deshacer después.

### Outbox

`SaleEvents.PAYMENT_CONFIRMED`/`COMPLETED` se encolan en `sales_outbox` dentro de la MISMA
transacción del paso anterior — si algo falla antes, ningún evento sobrevive (verificado con
test: una venta con pago incompleto no deja ninguna fila en `sales_outbox`).

### Cash effects — `SalesCashEffectsClient`

`backend/infrastructure/integrations/sales_cash_effects_client.py`. Conecta por primera vez
`CashSalesIntegrationService.record_completed_sale` (real, completo, encontrado sin conectar en
SALES-13) — agrupa `Sale.payments` por método en las líneas de liquidación que Caja espera
(`CASH`/`CARD`/`TRANSFER`/`CUSTOMER_CREDIT`/`MERCADO_PAGO`, vía `classify_settlement`).
**No se ejecuta dentro de la misma transacción atómica** (el hallazgo arquitectónico de arriba) —
se ejecuta DESPUÉS de que la venta ya quedó COMPLETED de forma durable, como efecto secundario de
mejor esfuerzo, registrado (`logger.warning`) y expuesto en el resultado
(`SaleResult.data["cash_effects_error"]`) sin jamás deshacer la venta. Es idempotente por diseño
(`record_completed_sale` ya no-opea si `find_payment_record_for_sale` encuentra un registro
previo) — seguro de reintentar desde un job de reconciliación futuro, que no se construyó aquí
(no existe ningún dispatcher de reintentos en este repositorio para nada, confirmado
repetidamente desde SALES-4).

### Inventory

`ConfirmInventoryReservationUseCase`'s lógica (SALES-9) ahora se ejecuta de verdad, dentro del
paso 2 del flujo atómico de arriba — cerrando el hueco que esa misma fase dejó explícitamente
documentado ("no wired into any real checkout flow").

### Loyalty — `RedeemLoyaltyPointsUseCase`

`backend/application/sales/use_cases/loyalty_use_cases.py`. El canje REAL que faltaba —
`SaleBenefitEvaluationService` (SALES-11) solo puede previsualizar. `SalesLoyaltyClient.redeem()`
(nuevo método) vuelve a previsualizar internamente para obtener el conteo de puntos YA
clamped/capeado por `LoyaltyService` antes de comprometerlo — nunca confía en el número crudo que
pidió el llamador, cerrando una condición de carrera real donde un monto sin validar podría
saltarse el tope del 50%/saldo disponible que `preview_redemption` ya aplica. El resultado reduce
`Sale.totals.loyalty_total` — el campo que `SaleTotals` reservó desde SALES-3 y que nunca nadie
había poblado. Nueva política `LoyaltyPolicy.ensure_can_redeem` (permite ACTIVE/CHECKOUT_PENDING/
PAYMENT_PENDING — más amplio que `SalePaymentPolicy`, ya que un cliente puede pedir canjear
puntos mientras aún arma el carrito, antes de que empiece el cobro).

**Permisos**: cero permisos nuevos — `RedeemLoyaltyPointsUseCase` reutiliza
`SalesPermissions.SALE_COMPLETE` (mismo razonamiento que `AssignCustomerToSaleUseCase`, SALES-6:
canjear puntos es una acción al servicio de completar una venta, no una capacidad independiente).

**Esquema**: `sales.loyalty_redeemed_amount` (columna nueva) + migración 202
(`ensure_column`, mismo patrón que 199). `SaleRepository` extendido para persistir/reconstruir.

### Tests

11 nuevos en `tests/unit/test_sales_checkout.py` (304 en total en la suite SALES-0..14, un solo
failure preexistente no relacionado ya documentado desde SALES-9), todos verdes en la primera
corrida real: checkout falla explícito con
pago incompleto sin dejar ningún rastro (ni inventario tocado ni evento en outbox — verificado
con una segunda venta paralela intocada), confirma inventario real y completa, completa sin
ninguna reserva, emite ambos eventos atómicamente, captura el error de efectos de caja sin
bloquear la venta cuando no hay turno de Caja abierto (el caso honesto y esperado dado que Caja y
Ventas todavía no comparten el mismo concepto de turno), y — con el esquema REAL de Caja
(`migrations.standalone.175_cash_register_bounded_context_schema`) y un turno abierto de verdad —
escribe una fila real en `cash_ledger_entries` tipo `CASH_SALE`. Fidelidad: falla sin cliente
asignado, falla sin puntos reales, canjea puntos reales y reduce el total exactamente por el
monto que Loyalty autorizó, es idempotente para la misma venta.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se resolvió el problema real de que `CashRegisterUnitOfWork` no soporta composición**
  (`owns_transaction`). Es un cambio del lado de Caja, fuera del alcance de una fase de "Ventas".
  Documentado como hallazgo real y persistente, no ocultado.
- **No se construyó ningún job de reconciliación** para reintentar `record_completed_sale` cuando
  falla (p. ej. sin turno abierto) — el error queda expuesto en el resultado del caso de uso,
  nada más. Ningún dispatcher de este tipo existe en ningún lado de este repositorio (mismo
  hallazgo repetido desde SALES-4/5/9).
- **No se unificó el concepto de "turno" entre Ventas y Caja.** La UI legacy sigue usando
  `turnos_caja`/`finance_service.get_estado_turno`; Caja usa `cash_shifts`. Esta fase conecta la
  pila nueva al concepto REAL de Caja (`cash_shifts`), no al legacy — son dos conceptos distintos
  y esta fase no los reconcilia.
- **Nada de esto se conectó a `modulos/ventas.py`.** El botón "Cobrar" real sigue llamando
  `finalizar_venta`/`_procesar_venta_via_uc` exactamente como antes.

## Siguiente fase

El master prompt continúa con POS-15 (Suspensiones — ya cubierto parcialmente por SALES-9) o
POS-16 (Cancelaciones y devoluciones) — confirmar alcance con el usuario antes de asumir.
