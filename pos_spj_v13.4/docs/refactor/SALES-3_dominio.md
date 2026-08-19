# SALES-3 — Dominio (POS-3 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-2_seguridad.md`.

## Alcance ejecutado

Master prompt §67, fase POS-3: "Sale. SaleLine. Totals. Policies. Events. Tests." Construye el
primer bounded context real (`backend/domain/sales/`) que `SALES-0_auditoria.md` había
confirmado que **no existía en absoluto** — solo había un `Sale`/`Money` muerto en el `domain/`
de raíz (float, ids enteros) que SALES-3 explícitamente NO reutiliza. Mirrors
`backend/domain/cash_register/entities.py` (mismo estilo: dataclasses `slots=True`, factories
`classmethod`, políticas que se validan antes de mutar) por ser el bounded context más cercano
en forma (agregado único con ciclo de vida + líneas), más que `backend/domain/inventory/` (una
docena de entidades independientes).

## Entregables

**Value objects** (`backend/domain/sales/value_objects/`):
- `money.py` — `money(value, *, allow_zero=True, allow_negative=False)`, Decimal-only, mirrors
  `cash_register`'s propia función.
- `quantity.py` — `Quantity` (Decimal + unidad, siempre > 0 — remover una línea es
  `remove_line`, no `quantity=0`).
- `sale_totals.py` — `SaleTotals` (§27: `gross_subtotal`, `discount_total`, `promotion_total`,
  `coupon_total`, `loyalty_total`, `tax_total`, `rounding_adjustment`, `total`), valida en
  construcción que `total` coincide exactamente con la suma de sus componentes — nunca se
  ensambla a mano fuera de `SaleTotalsService`.

**Dominio de agregado** (`backend/domain/sales/entities.py`):
- `SaleLine` — `id`, `sale_id`, `product_id`, `quantity: Quantity`, `unit_price`,
  `product_snapshot` (dict libre, preserva nombre/sku/etc. al momento de agregar — §11: "no
  reconstruir ventas históricas con datos actuales"), `pricing_snapshot_id`, `discount_total`,
  `tax_total`, `weight_source`, `lot_reference`, `created_at`/`updated_at`. `line_total` es una
  `@property` derivada (nunca almacenada) para que no pueda desincronizarse de sus componentes.
- `Sale` (aggregate root) — `id`, `branch_id`, `cashier_user_id`, `operation_id`, `status`,
  `sale_number`, `workstation_id`, `cash_session_id`, `customer_id`, `channel`,
  `currency_code`, `lines: list[SaleLine]`, `totals: SaleTotals`, `created_at`/`suspended_at`/
  `completed_at`/`cancelled_at`, `version` (concurrencia optimista).
  Métodos: `start` (factory), `add_line`/`update_line_quantity`/`remove_line`,
  `apply_line_discount`/`apply_sale_discount`, `assign_customer`, `begin_checkout`/
  `mark_payment_pending`/`complete`, `suspend`/`resume`, `cancel`. Cada mutación pasa primero
  por su política, luego muta estado, recalcula totales vía `SaleTotalsService` y aumenta
  `version`.

**Decisión de diseño explícita, distinta del listado plano del master prompt §10**: `Sale` no
tiene 4 campos sueltos `subtotal`/`discount_total`/`tax_total`/`total` — tiene un único
`totals: SaleTotals` (la VO más rica de §27). El listado del prompt sugiere ambos; se
reconcilió a favor de una sola fuente de verdad, exactamente el principio que el propio
prompt declara en su §73 ("Una sola evaluación de precios") — mantener las 4 versiones planas
en paralelo a la VO habría sido la duplicación que el resto del documento prohíbe.

**Políticas** (`backend/domain/sales/policies/`, funciones puras, sin I/O — el caller ya
resolvió cualquier dato externo):
- `lifecycle_policies.py` — `SaleLifecyclePolicy` (tabla de transición completa de los 10
  estados de §10, mirrors `CashShiftLifecyclePolicy`), `CheckoutPolicy` (§13/§38: no checkout
  sin líneas ni total > 0), `SaleCancellationPolicy` (§42: una venta `COMPLETED` no se cancela,
  se reversa).
- `suspension_policies.py` — `SaleSuspensionPolicy` (límite de ventas suspendidas concurrentes,
  §41), `SaleResumptionPolicy` (reglas cross-user/cross-workstation, §41).
- `line_policies.py` — `SaleLinePolicy` (cuándo se pueden mutar líneas), `QuantityPolicy`
  (cantidad > 0, límite `max_sellable` opcional).
- `discount_policy.py` — `SaleDiscountPolicy` (§25-26: por encima de 20% requiere
  autorización — la política solo decide SI se requiere; la autorización real la valida
  `SalesAuthorizationPolicy` de SALES-2, nunca duplicada aquí).
- `customer_assignment_policy.py` — `CustomerAssignmentPolicy` (§21: se puede asignar/cambiar
  cliente hasta `CHECKOUT_PENDING`, no después).
- `sale_creation_policy.py` — `SaleCreationPolicy` (§13: gate de sesión de caja abierta, el
  caller ya resolvió el estado real).

**Decisión de diseño documentada**: el listado de políticas del master prompt §8.2 incluye
`sale_authorization_policy` dentro de `domain/policies/` — **no se duplicó aquí**.
`SalesAuthorizationPolicy` ya vive en `backend/application/sales/authorization.py` desde
SALES-2 y requiere un `PermissionChecker` inyectado (I/O-adjacent), lo que lo hace
application-layer por definición en este repositorio (mismo patrón ya usado por
Inventario/Customer Master) — dominio nunca depende de infraestructura de permisos.

**Servicio de dominio** (`backend/domain/sales/services/sale_totals_service.py`):
- `SaleTotalsService.calculate(lines, *, sale_level_discount=0, promotion_total=0,
  coupon_total=0, loyalty_total=0, rounding_adjustment=0) -> SaleTotals` — el único lugar que
  suma líneas; `Sale._recalculate_totals()` lo llama después de cada mutación.

**Eventos** (`backend/domain/sales/events.py`):
- `SaleEvents` — los 17 eventos canónicos exactos de §60 (`SALE_STARTED` .. 
  `SALE_RECEIPT_REPRINT_REQUESTED`), `sale_event_payload()` (mirrors `cash_event_payload`,
  valida UUIDv7 en todos los ids, genera `event_id` distinto de `operation_id`/`entity_id`).

**Tests** (69 nuevos en `tests/unit/test_sales_domain.py`, todos verdes): value objects
(`Quantity`, `money`, `SaleTotals`), `SaleTotalsService`, las 9 clases de política, `SaleLine`,
el agregado `Sale` completo (ciclo de vida feliz + cada rechazo de política), y el catálogo de
eventos.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **`SaleEvents` no está cableado al `EventBus` real.** Es el vocabulario objetivo para cuando
  una fase futura migre casos de uso reales al agregado `Sale` — el vocabulario legacy que
  hoy mueve producción (`VENTA_COMPLETADA`/`SALE_CREATED`, `VENTA_CANCELADA`,
  `VENTA_SUSPENDIDA`, `SALE_ITEMS_PROCESS` en `core/events/domain_events.py` +
  `core/events/wiring.py`) sigue siendo el único que realmente dispara handlers hoy. Ver
  docstring propio de `events.py`.
- **Ningún caso de uso real llama a `Sale.start()`/`add_line()`/etc.** `modulos/ventas.py` y
  `core/services/sales_service.py` siguen siendo la ruta operativa real (confirmado en
  SALES-0) — este agregado es dominio puro, listo para que una fase de aplicación
  (`backend/application/sales/use_cases/`, no construida aún) lo orqueste.
- **No se implementaron transiciones de devolución/reverso en el agregado** (`RETURNED_PARTIALLY`/
  `RETURNED_FULLY`/`REVERSED` existen como estados válidos en `SaleStatus` y en la tabla de
  transición, pero `Sale` no tiene métodos `return_items()`/`reverse()` todavía — la lógica real
  de devoluciones/reversos ya existe y funciona en `core/services/sales_reversal_service.py`
  (SALES-0 la calificó de "genuinamente atómica, con triggers de guardia"); reconciliar ambas
  rutas es trabajo de una fase posterior (POS-16 en la numeración del prompt), no de esta.
- **Sin persistencia.** No hay repositorio (`backend/infrastructure/db/repositories/sales/`)
  que guarde/reconstruya un `Sale` desde SQLite todavía — eso es POS-5 en el prompt.
- **`weight_source`/`lot_reference` son campos de paso** (strings libres) — la captura real de
  peso vía báscula (§19, `ScaleGateway`) es trabajo de POS-12, ya identificado como gap en
  `SALES-0_auditoria.md`.

## Siguiente fase

El master prompt continúa con POS-4 (Esquema limpio: UUIDv7, Decimal, Constraints, Índices,
Outbox) o POS-5 (Repositorios y UoW) — confirmar con el usuario antes de asumir orden.
