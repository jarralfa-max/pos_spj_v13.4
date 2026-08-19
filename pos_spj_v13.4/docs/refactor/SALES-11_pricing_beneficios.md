# SALES-11 — Pricing y beneficios (POS-11 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-10_cliente.md`.

## Alcance ejecutado

Master prompt §67, fase POS-11: "Effective price. Promotions. Loyalty. Coupons. Vouchers.
Tests." Sección 24 (BENEFICIOS Y PROMOCIONES) pide un `SaleBenefitEvaluationDTO` que separe:
descuento comercial, promoción, cupón, puntos, vale, autorización manual. Investigué primero
(agente de research) qué existe realmente de cada uno de los cinco dominios nombrados antes de
diseñar nada — el resultado fue una frontera muy clara entre "integrar algo real" y "no hay
nada aquí, sería trabajo nuevo".

## La frontera real, confirmada por investigación

| Dominio | Estado real |
|---|---|
| **Pricing** | Bounded context completo y real (`backend/domain/pricing/`, `backend/application/pricing/`). `PricingReadFacade.sale_price(...)` ya resuelve precio por sucursal, por cliente y por volumen — Decimal de punta a punta, documentado como "single canonical read entry for the 44 consumers". |
| **Promotions** | **No existe.** Sin `backend/domain/promotions/`, sin `backend/application/promotions/`, sin tabla de promociones en ningún esquema. `PriceListKind.PROMOTIONAL` es un valor de enum muerto — nunca se consulta en `ProductPriceQueryService`. |
| **Loyalty** | Solo el legacy `core/services/loyalty_service.py::LoyaltyService.preview_redemption` es una evaluación real y sin efectos secundarios ("Seguro para llamar antes de confirmar el pago", su propio docstring). La capa `backend/` nueva solo tiene lectura de resumen estático (`LoyaltyCustomerSummaryQuery`), no evaluación de carrito. |
| **Coupons** | **No existe** ningún catálogo operativo (código, descuento, vigencia). Solo existe la cola de reconocimiento contable en Finanzas (`commercial_obligations`, tipo `PROMOTIONAL_COUPON`/`DISCOUNT_COUPON`) — reacciona a una decisión de cupón ya tomada en otro lugar que no existe. |
| **Vouchers** | Mismo caso que Coupons — solo el reconocimiento contable posterior existe. |

Fabricar un motor de Promociones/Cupones/Vales en esta fase habría sido exactamente el tipo de
infraestructura decorativa que esta pipeline ya se ha negado a construir repetidamente sin un
punto de integración real (el dispatcher de outbox nunca construido en SALES-4/5/9, el
scheduler nunca construido en CRM-26). Esos tres campos del DTO quedan en 0 con una advertencia
explícita, no ocultos ni fabricados.

## Entregables

**Infraestructura** (mirrors `sales_inventory_client.py`/`sales_customer_client.py`):
- `backend/infrastructure/integrations/sales_pricing_client.py::SalesPricingClient` —
  `effective_price(product_id, *, branch_id, customer_id, quantity)`, delega completo a
  `PricingReadFacade`. Ya es Decimal-first del lado de Pricing — sin conversión de frontera
  necesaria aquí (a diferencia de Inventory/Loyalty, que siguen siendo float legacy).
  **Deliberadamente NO conectado a `SalesCatalogQueryService.search()`** (SALES-7): esa
  consulta hace un solo SQL masivo para toda la grilla del catálogo; resolver cada fila vía
  `PricingReadFacade` significaría una consulta por producto (N+1). Este cliente sirve para
  resolver el precio real de UN producto específico para un cliente/cantidad específicos, en
  el momento en que sí importa (antes de agregar la línea al carrito), no para poblar la
  grilla completa.
- `backend/infrastructure/integrations/sales_loyalty_client.py::SalesLoyaltyClient` —
  `preview_redemption(customer_id, subtotal)`. Cruza DOS fronteras explícitas: (1) identidad —
  `Sale.customer_id` es un `customers.id` de Customer Master, pero `LoyaltyService` solo
  entiende `clientes.id` legacy, puenteado vía `EnsureLegacyCustomerBridgeUseCase` (CRM-21,
  dirección nuevo→legacy — la inversa de la que `ScanLoyaltyCardForSaleUseCase` ya usa en
  SALES-10 para legacy→nuevo); (2) Decimal→float, la única conversión de este tipo en toda la
  ruta de evaluación de beneficios.

**Aplicación**:
- `SaleBenefitEvaluationDTO` (`backend/application/sales/dto.py`) — exactamente las seis
  categorías de §24.
- `SaleBenefitEvaluationService` (`backend/application/sales/queries/
  benefit_evaluation_service.py`) — mirrors el patrón de composición ya establecido en
  `Customer360QueryService` (confirmado por investigación como el precedente real de este
  repositorio para "componer salidas de varios bounded contexts en un solo DTO, una sola
  puerta dura, todo lo demás se degrada de forma independiente"): la venta debe existir (única
  puerta dura), la evaluación de fidelidad se degrada a cero + advertencia ante cualquier
  fallo (cliente sin asignar, programa deshabilitado, excepción de infraestructura) sin
  interrumpir el resto del breakdown.

**Descuento comercial ya era real** (no se construyó nada nuevo): `SaleDiscountPolicy` +
`Sale.apply_line_discount`/`apply_sale_discount` (SALES-3, ya fluyendo a `SaleTotals.
discount_total` desde el principio) — esta fase solo lo expone a través del nuevo DTO,
incluyendo la bandera `requires_manual_authorization` (misma política, aplicada de forma
consultiva sobre el descuento ya vigente de la venta).

**Tests** (12 nuevos, todos verdes en la primera corrida — la investigación previa evitó
depuración de esquema; 233 en total en la suite SALES-0..11, cero regresiones): precio efectivo
resuelve base/sucursal/no-configurado, preview de fidelidad puentea identidad y refleja saldo
real, evaluación de beneficios exige permiso y venta existente, sin cliente asignado degrada
correctamente con advertencia, promoción/cupón/vale siempre en cero con las tres advertencias
explícitas, descuento comercial grande marca `requires_manual_authorization=True` (chico no lo
marca), y cliente con puntos reales produce un preview de redención mayor a cero.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se construyó ningún motor de Promociones, Cupones o Vales.** Los tres campos del DTO
  quedan en `Decimal("0")` para siempre hasta que exista un bounded context real que evaluar —
  no es una limitación temporal de esta fase, es un hueco real y documentado del
  repositorio completo.
- **No se conectó `SalesPricingClient` a `SalesCatalogQueryService`** (razón: N+1, documentada
  arriba) ni a `AddSaleLineUseCase` (que sigue recibiendo `unit_price` como parámetro explícito
  del llamador — resolver el precio real antes de llamarlo es composición del caller, no un
  cambio de contrato del use case existente).
- **"Puntos a ganar" (§29) no se evaluó** — el campo `loyalty_points_available` de esta fase es
  sobre REDENCIÓN disponible (un beneficio real que reduce el total actual), no sobre una
  proyección de puntos a ganar tras completar la compra; la sección 29 del prompt es una
  sección distinta de la 24, y POS-11 no la nombra en su propia lista de acciones. Además, se
  confirmó que el "puntos a ganar" que hoy muestra la UI legacy
  (`core/services/sales/cart_calculator.py::puntos_preview`) es un placeholder ingenuo
  (`int(total_final)`, 1:1), no fidelidad real — hallazgo honesto, no corregido en esta fase.
- **Nada de esto se conectó a `modulos/ventas.py`.** El diálogo de pago legacy sigue llamando
  `loyalty_service.preview_redemption` directamente desde la UI (hallazgo original de SALES-0,
  sin cambios).

## Siguiente fase

El master prompt continúa con POS-12 (Hardware: Scanner, Scale, Terminal, Drawer, Customer
display, Tests). Confirmar alcance con el usuario antes de asumir — SALES-0 ya encontró que el
cajón de dinero está bien abstraído (`hardware_service.open_cash_drawer()`) pero la báscula usa
`serial.Serial` directo con `COM3` hardcodeado ignorando un `ScaleGateway` ya existente, y hay
dos implementaciones paralelas de captura de scanner.
