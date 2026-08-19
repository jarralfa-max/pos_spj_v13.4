# SALES-8 — Carrito (POS-8 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-7_catalogo.md`.

## Alcance ejecutado

Master prompt §67, fase POS-8: "Add. Update. Remove. Totals. Tests." Tal como anticipó
`SALES-7_catalogo.md`, la mayor parte de esto ya existía — SALES-3 construyó el dominio
(`Sale.add_line`/`update_line_quantity`/`remove_line`, `SaleTotalsService`) y SALES-6 construyó
los casos de uso de aplicación (`AddSaleLineUseCase`/`UpdateSaleLineQuantityUseCase`/
`RemoveSaleLineUseCase`). Esta fase fue de verificación de huecos, no de construcción desde
cero — y encontró dos reales.

## Hallazgo 1: faltaba `ApplyLineDiscountUseCase`

La sección 12 del master prompt (CARRITO CANÓNICO) nombra explícitamente 6 acciones del
carrito: `AddSaleLineUseCase`, `UpdateSaleLineQuantityUseCase`, `RemoveSaleLineUseCase`,
`ApplyLineDiscountUseCase`, `ApplySaleDiscountUseCase`, `AssignCustomerToSaleUseCase`. SALES-6
construyó 5 de las 6 — **`ApplyLineDiscountUseCase` nunca se construyó**, a pesar de que el
método de dominio que envuelve (`Sale.apply_line_discount`, existente desde SALES-3) ya estaba
completo y probado a nivel de agregado. Se cerró en esta fase: `backend/application/sales/
use_cases/discount_use_cases.py::ApplyLineDiscountUseCase`, espejo exacto de
`ApplySaleDiscountUseCase` (mismo mecanismo de autorización en caliente vía
`SalesAuthorizationPolicy.authorize_exception`, mismo mapeo de errores), pero dirigido a una
línea específica en vez de al total de la venta.

## Hallazgo 2: `SaleDTO` solo exponía 4 de los 8 campos de `SaleTotals`

`SaleDTO` (construido en SALES-6) solo tenía `gross_subtotal`/`discount_total`/`tax_total`/
`total` — faltaban `promotion_total`, `coupon_total`, `loyalty_total`, `rounding_adjustment`,
los otros 4 campos que `SaleTotals` (SALES-3, §27) ya calcula y valida internamente. Un
consumidor del DTO (la futura UI) no tenía forma de mostrar el desglose completo sin volver a
tocar la entidad de dominio directamente — exactamente lo que un DTO existe para evitar. Se
extendió `SaleDTO.from_entity()` para exponer los 8 campos completos.

## Entregables

- `backend/application/sales/use_cases/discount_use_cases.py::ApplyLineDiscountUseCase` (nuevo).
- `backend/application/sales/dto.py::SaleDTO` extendido con `promotion_total`/`coupon_total`/
  `loyalty_total`/`rounding_adjustment`.
- Limpieza menor: `ApplySaleDiscountUseCase` tenía dos bloques `except` redundantes
  (`DiscountNotAllowedError` seguido de `SalesDomainError`, siendo el primero ya subclase del
  segundo) — consolidados en uno solo, sin cambio de comportamiento.

**Tests** (13 nuevos, todos verdes en la primera corrida; 195 en total en toda la suite
SALES-0..8, sin regresiones):
- `TestApplyLineDiscountUseCase` (5): descuento pequeño sin autorización, descuento grande
  denegado sin autorizador, descuento grande permitido con autorización en caliente válida,
  auto-autorización rechazada, línea inexistente falla con `LINE_NOT_FOUND`.
- `TestCartTotals` (2): el DTO expone los 8 campos completos de `SaleTotals` (no solo los 4 que
  existían antes de esta fase); descuento de línea + descuento de venta se combinan
  correctamente en `discount_total` — verificado end-to-end, no solo a nivel de
  `SaleTotalsService` (que SALES-3 ya probó de forma aislada).

## Lo que esta fase NO hizo (honesto, no fabricado)

- **`SaleCart`/`SaleCartLineViewModel` (§12) no se construyeron como clases separadas.**
  `SaleDTO`/`SaleLineDTO` (SALES-6, extendido aquí) ya cumplen exactamente el rol que el prompt
  describe ("El carrito de UI es una proyección de Sale") desde el backend — las clases
  específicas de PyQt (`ViewModel`/`TableModel` reales que una ventana instanciaría) son trabajo
  de UI, explícitamente POS-19 en la lista de fases del propio prompt, igual que la búsqueda de
  POS-7.
- **No se tocó ningún consumidor real.** `modulos/ventas.py` sigue construyendo su carrito como
  lista de diccionarios (`self.compra_actual`) — el hallazgo original de SALES-0/master prompt
  §12 ("no mantener la compra como lista de diccionarios sin reglas") sigue sin resolverse en la
  UI real. Esta fase deja el reemplazo backend completo y probado, no lo conecta.
- **Promoción/cupón/lealtad siguen en cero siempre** — los campos existen en el DTO y en
  `SaleTotals` desde SALES-3, pero ningún caso de uso de esta pipeline los alimenta todavía
  (requiere integración real con Promotions/Loyalty, fuera de alcance de Carrito).

## Siguiente fase

El master prompt continúa con POS-9 (Inventory reservations: Reserve, Confirm, Release,
Expire, Tests). SALES-0 ya identificó que `StockReservationService` legacy es sólido y
reutilizable — esa fase probablemente sea sobre conectar el agregado `Sale` nuevo a esa
reserva existente, no reconstruirla. Confirmar alcance con el usuario antes de asumir.
