# INV-27 — Reporte de eliminación de legacy (cutover flag-gated)

Estado: **cutover preparado y gated OFF**. El contexto canónico de inventario
(INV-1…INV-25) se construyó como **paralelo born-clean**; sus handlers postean al
ledger canónico pero **no** estaban cableados al EventBus vivo. Esta fase entrega
el **flip controlado** sin ejecutar todavía ningún DROP destructivo (decisión:
"flag-gated, no drops yet"), porque los lectores operativos legacy aún no están
repunteados.

## Qué entrega INV-27 (reversible, sin romper nada)

| Componente | Rol | Estado |
|---|---|---|
| `backend/application/inventory/cutover/canonical_cutover.py` | `is_cutover_enabled` (flag env `INVENTORY_CANONICAL_CUTOVER` o setting GLOBAL `canonical_cutover_enabled`) + `CanonicalInventoryCutover.wire/unwire/neutralize_legacy` | ✅ gated **OFF** por defecto |
| `backend/application/inventory/cutover/reconciliation.py` | `InventoryReconciliationService` — compara disponible canónico (`inventory_balances`) vs stock legacy (`inventario_actual`/`inventory_stock`), reporta drift; `is_in_sync()` | ✅ |
| `migrations/deferred/legacy_inventory_drop.py` | DROP de tablas/triggers legacy, **NO registrado** en `engine.py`, **env-guard** `INVENTORY_ALLOW_LEGACY_DROP=1` | ✅ diferido, nunca corre solo |
| Tests `test_inventory_cutover.py` | flag OFF/ON, wiring canónico + neutralización legacy, evento→ledger, reconciliación paridad/drift, guard del drop, no-registrado-en-engine | ✅ 12 |

## Handlers canónicos que toman el control en el flip

`CANONICAL_HANDLER_CLASSES` (cada uno consume su `event_name` vivo):

| Handler | Evento vivo | Movimiento canónico |
|---|---|---|
| `SaleIssueHandler` | `SALE_CONFIRMED` | SALE_ISSUE |
| `CustomerReturnHandler` | `CUSTOMER_RETURN_CONFIRMED` | SALE_RETURN → PENDING_INSPECTION |
| `PurchaseReceiptHandler` | `GOODS_RECEIPT_COMPLETED` | PURCHASE_RECEIPT (+lote/costo/calidad) |
| `DirectPurchaseReceiptHandler` | `DIRECT_PURCHASE_RECEIVED` | PURCHASE_RECEIPT |
| `SupplierReturnHandler` | `PURCHASE_RETURN_CREATED` | SUPPLIER_RETURN |
| `GoodsReceiptReversedHandler` | `GOODS_RECEIPT_REVERSED` | REVERSAL |
| `ProductionExecutionHandler` | `PRODUCTION_COMPLETED` | PRODUCTION_CONSUMPTION + PRODUCTION_OUTPUT |

## Secuencia del corte real (cuando se decida ejecutarlo)

1. **Repuntar lectores** operativos legacy (POS/BI/producción) a
   `InventoryAvailabilityQueryService` / `inventory_balances`. *(pendiente, gran
   esfuerzo transversal — fuera del alcance de esta fase por diseño).*
2. **Encender el flag** (`INVENTORY_CANONICAL_CUTOVER=1` o setting GLOBAL) y
   cablear en el bootstrap: `CanonicalInventoryCutover(conn).wire(bus,
   legacy_handlers=[…])` — subscribe canónicos y **neutraliza** los legacy
   (evita doble descuento).
3. **Verificar paridad**: `InventoryReconciliationService(conn).is_in_sync()`.
4. **DROP legacy**: correr manualmente `migrations/deferred/legacy_inventory_drop`
   con `INVENTORY_ALLOW_LEGACY_DROP=1`.
5. **Reclamar nombres** (`inventory_ledger` → `inventory_movements`, plurales) en
   un paso de rename separado — diferido para no romper referencias canónicas.

## Tablas legacy objetivo del DROP diferido

`inventario_actual`, `inventory_stock`, `branch_inventory`, `inventario_diario/
global/subproductos/sucursal`, `inventory_movements`(098), `movimientos_inventario`,
`movimientos_lote`, `movimientos_trazabilidad`, `transferencias`,
`transferencias_inventario`, `traspasos`, `recepciones`, `ajustes_inventario`,
`stock_reservas(+detalle)`, `inventory_reservations`, `lotes`.
Triggers: `trg_sync_existencia_*`, `trg_recalc_inventario_actual`.

## Riesgo controlado

- Nada en runtime cambia con el flag OFF: la app sigue usando el path legacy.
- El DROP no puede ejecutarse por accidente (no está en `engine.py` y exige
  env-guard explícito).
- La reconciliación permite **probar** paridad antes de arriesgar el flip.
- `unwire`/`neutralize_legacy` hacen el flip reversible en caliente.
