# G0 — Auditoría de paridad de escritura de stock

Prerequisito del cutover de lectura de stock (ver `stock_read_cutover_plan.md`).
Clasifica los **9 escritores** de `productos.existencia` y verifica si la
proyección canónica `inventory_balances` se alimenta de las mismas operaciones,
para decidir si se puede repuntar lecturas (Fase A/B) y qué se neutraliza
(Fase C).

_Método: lectura del grafo de wiring de eventos (`core/events/wiring.py`), de los
handlers canónicos y de los escritores legacy; ejecución de `is_cutover_enabled`
y `InventoryReconciliationService.drifts()` sobre una DB bootstrapped._

---

## 1. Dos modelos de stock coexisten

- **Legacy**: `inventario_actual` + `movimientos_inventario` + `branch_inventory`
  + `productos.existencia` (cache denormalizada, suma por sucursal).
- **Canónico**: `inventory_ledger` + `inventory_balances` (INV-2…27).

`is_cutover_enabled` → **True** en toda DB bootstrapped (la migración 134 fija el
setting `canonical_cutover_enabled=true`). El `CanonicalStockReadAdapter` ya sirve
canónico cuando el flag está ON.

## 2. Hallazgo clave — el canónico está **fresco** (dual-fed), no obsoleto

El wiring canónico está suscrito para los flujos vivos:

- **Venta**: `SALE_ITEMS_PROCESS` → `CanonicalSaleInventoryHandler` postea
  `SALE_ISSUE` en el ledger dentro del SAVEPOINT de la venta. El comentario del
  wiring afirma: *"the legacy UnifiedInventoryService.decrease_stock path was
  removed"*.
- **Compra**: `PURCHASE_STOCK_ENTRY_REGISTERED` → `CanonicalPurchaseStockEntryHandler`
  (bridge) — *"Replaces the legacy PurchaseStockEntryHandler / PurchaseLotEntryHandler"*.
- El handler legacy `PurchaseStockEntryHandler` **no aparece suscrito** en el bus
  (sólo su reemplazo canónico).

**Consecuencia:** `inventory_balances` refleja los movimientos vivos → repuntar
lecturas al canónico (Fase A/B) es **seguro ahora** (con el adapter gated + G1),
porque el canónico no es un snapshot rancio. Esto **relaja** el bloqueo que el
plan anotó como duro: el gate duro sólo aplica a Fase C (neutralización de
escritura) y E (DROP).

## 3. Matriz de paridad de los 9 escritores

| # | Escritor (`SET existencia`) | Operación | Canónico equivalente (wired) | Clasificación | Acción (fase) |
|---|------|-----------|------------------------------|---------------|---------------|
| 1 | `event_handlers/inventory/purchase_stock_entry_handler.py` | recepción compra | `CanonicalPurchaseStockEntryHandler` (bridge, wiring 313) | **Superseded** — no suscrito en el bus | Eliminar (C) tras confirmar 0 callers vivos |
| 2 | `infrastructure/db/repositories/compras_write_repository.py` | recepción/devolución compra | bridge de compra → `inventory_balances` | Legacy repo; confirmar callers vivos | Neutralizar (C) |
| 3 | `core/services/inventory/unified_inventory_service.py` | ajuste/movimiento genérico | `AJUSTE_INVENTARIO` / `PostInventoryMovement`; ruta `decrease_stock` ya removida de venta | Legacy vivo (producción, `repositories/ventas.py`) | Neutralizar (C) tras paridad por operación |
| 4 | `core/services/lote_service.py` | alta de lote añade stock | `PurchaseLotEntryHandler` canónico | Legacy vivo | Neutralizar (C) |
| 5 | `core/services/sales_service.py` | venta directa descuenta stock | `SALE_ISSUE` (ruta viva de checkout) | Legacy vivo (ruta directa secundaria) | Neutralizar (C) — **crítico, último** |
| 6 | `integrations/pos_adapter.py` | venta WhatsApp descuenta stock | `SALE_ISSUE` | Legacy vivo (`pedido_wa`) | Neutralizar (C) |
| 7 | `services/qr_service.py` | recepción QR añade stock | recepción QR canónica (PUR-13) | Legacy vivo | Neutralizar (C) |
| 8 | `repositories/inventory_repository.py` | `existencia = SUM(inventario_actual)` | — (la proyección canónica es `inventory_balances`) | **Sync de cache** (no fuente) | Se elimina con el modelo legacy (C/E) |
| 9 | `repositories/productos.py` | alta de producto (existencia inicial) | `products` (sin existencia) | Escritura de creación legacy | Se va con el DROP (E) |

## 4. Confirmaciones abiertas antes de Fase C (no bloquean A/B)

- **G0.a** — Para cada escritor #2–#7, confirmar que **toda ruta viva que lo
  invoca también emite el evento canónico** correspondiente (`SALE_ITEMS_PROCESS`,
  `AJUSTE_INVENTARIO`, `PRODUCCION_COMPLETADA`, `PURCHASE_STOCK_ENTRY_REGISTERED`,
  recepción QR). Si alguna ruta escribe legacy sin emitir canónico, neutralizarla
  perdería el movimiento → primero cablear el evento.
- **G0.b** — Confirmar que #1 (`PurchaseStockEntryHandler`) no tiene callers
  directos fuera del bus antes de eliminarlo.
- **G0.c** — Ejecutar `InventoryReconciliationService.drifts()` sobre datos
  representativos (no vacíos). En bootstrap vacío el drift es **0** y el flag ON;
  en datos reales el drift debe explicarse (el propio 134 registra drift esperado
  mientras los escritores legacy sigan vivos).

## 5. Conclusión

- **Fase A/B (repunte de lecturas): DESBLOQUEADA.** El canónico está dual-fed y
  fresco para venta y compra; con el `CanonicalStockReadAdapter` (gated + fallback)
  y `InventoryStockAggregateQueryService` (G1), repuntar lectores es seguro y
  reversible.
- **Fase C (neutralización de escritura): gated por G0.a/G0.b** — cleanup de la
  escritura legacy redundante, por operación, con `sales_service` al final.
- **Fase E (DROP): gated por allowlist vacía + reconciliación sin drift.**

Recomendación de secuencia revisada: **A → B → D → (G0.a/b por operación) → C → E**.
