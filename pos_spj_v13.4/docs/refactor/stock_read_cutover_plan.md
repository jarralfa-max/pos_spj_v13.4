# Plan — Cutover de lectura de stock (`existencia` → `inventory_balances`)

Plan (no ejecución) para destrabar el bloque de consumidores legacy de
`productos` que dependen de **existencia**. Es la continuación de INV-27 acotada
al corte del maestro de Productos: mientras las lecturas de stock sigan en
`productos.existencia`, ~33 archivos no pueden delistarse del ratchet
(`test_products_legacy_consumers_ratchet`) y el DROP de `productos` queda
bloqueado.

> Regla rectora (INV-27): **las lecturas siguen a las escrituras.** Repuntar un
> lector a canónico sólo es correcto si la escritura de ese stock ya es canónica;
> de lo contrario se sirve un snapshot obsoleto.

---

## 1. Estado actual (verificado en código)

- **Adapter strangler** `core/services/inventory/canonical_stock_read_adapter.py`
  (`CanonicalStockReadAdapter`): `available()/available_float()`, **gated** por
  `is_cutover_enabled`. Con flag ON lee `inventory_balances` (canónico); con flag
  OFF devuelve el callable legacy inyectado → repuntar con flag OFF es un no-op
  seguro, y el switch a canónico es atómico al prender el flag.
- **Flag** `backend/application/inventory/cutover/canonical_cutover.py::is_cutover_enabled`:
  OFF por defecto; ON por env `INVENTORY_CANONICAL_CUTOVER` truthy **o** por el
  setting global `canonical_cutover_enabled='true'`.
- **Migración 134** (`134_inventory_canonical_cutover`): backfill legacy→canónico
  (saldos de apertura `ADJUSTMENT_IN`) → snapshot de reconciliación → **fija el
  setting `canonical_cutover_enabled=true`**. Está en la cadena de migraciones →
  en toda DB bootstrapped/producción el flag queda **ON**.
- **Lectura canónica de disponibilidad**:
  `backend/application/inventory/queries/availability_query_service.py::
  InventoryAvailabilityQueryService.get_availability(product_id, branch_id) → Decimal`.
- **Reconciliación**: `backend/application/inventory/cutover/reconciliation.py::
  InventoryReconciliationService.drifts()`.

### Consumidores de `productos.existencia` en el ratchet (33)

- **9 escritores** (`UPDATE productos SET existencia …`):
  `sales_service`, `lote_service`, `pos_adapter`, `qr_service`,
  `inventory_repository`, `compras_write_repository`,
  `unified_inventory_service`, `purchase_stock_entry_handler`, `repositories/productos`.
- **24 lectores** (scalar o agregado sobre `existencia`): `product_query_service`,
  `product_repository`, `product_catalog_service`, `inventory_balance_service`
  (×2), `purchase_planning_query_service`, `app_container`, `health_server`,
  `actionable_forecast`, `alert_engine`, `alertas_service`, `analytics_engine`,
  `decision_engine`, `demand_forecasting`, `report_engine`(×2),
  `erp_application_service`, `export_service`, `treasury_service`,
  `forecast_engine`, `forecast_service`, `production_query_service`,
  `reporte_email_service`, `main_window_repository`.

## 2. Bloqueador crítico — G0: neutralización de escritura

**Hallazgo:** `core/services/sales_service.py` (línea ~1583) ejecuta
`UPDATE productos SET existencia = COALESCE(existencia,0) - ? WHERE id=?`
**sin gate**. Es decir, existe (al menos) un camino de venta legacy que mantiene
`productos.existencia` vivo, en paralelo a la escritura canónica del ledger. Con
un escritor legacy vivo, "las lecturas siguen a las escrituras" **no se cumple**:
canónico podría quedar atrás de `productos.existencia` para ese flujo.

**Por tanto, antes de repuntar lecturas hay que resolver G0:**

| Paso | Entregable |
| ---- | ---------- |
| G0.1 | **Matriz de paridad de escritura** de los 9 escritores: clasificar cada uno en (a) escritura legacy muerta (el flujo ya postea movimiento canónico), (b) escritura legacy viva a neutralizar, (c) doble escritura. |
| G0.2 | Confirmar que **toda** operación que mueve stock (venta, producción, transferencia, compra/recepción, merma, ajuste, QR) postea a `inventory_balances` vía su handler/UoW canónico. |
| G0.3 | Ejecutar `InventoryReconciliationService.drifts()` sobre datos reales/representativos; el drift debe estar explicado o en cero para los productos en alcance. |

G0 es **prerequisito duro**. Sin él, cualquier repunte de lector es potencialmente
regresivo.

## 3. Distinción de lectores (define la técnica de repunte)

- **Lectores escalares de disponibilidad** (`existencia` de un producto/sucursal):
  → `CanonicalStockReadAdapter.available(product_id, branch_id)`. Repunte directo,
  con fallback legacy → no-op si el flag está OFF. Ej.: `pos_adapter.get_stock`,
  `main_window_repository`, chequeos puntuales.
- **Lectores agregados** (`SUM(existencia)`, conteos `existencia<=stock_minimo`,
  KPIs de stock bajo): NO pueden usar el adapter por-fila; requieren una **consulta
  canónica agregada** sobre `inventory_balances` (p. ej. un
  `InventoryStockAggregateQueryService` a crear, o reutilizar los servicios BI de
  inventario ya migrados). Ej.: `health_server`, `reporte_email_service`,
  `alert_engine`, `report_engine`, `forecast_*`, `analytics_engine`.
- **Lectores `SELECT *`** (`product_query_service.get_product`,
  `product_repository.get`): componen el dict con todas las columnas legacy incl.
  `existencia`; se repuntan a `products` + satélites + disponibilidad canónica en
  una fase final.

## 4. Plan por fases

| Fase | Alcance | Riesgo | Salida |
| ---- | ------- | ------ | ------ |
| **G0** | Matriz de paridad de escritura + reconciliación (§2) | — (auditoría) | Doc de paridad + drift ≈ 0 |
| **G1** ✅ | `InventoryStockAggregateQueryService` canónico (`available_by_product`, `total_available`, `low_stock_items/count`) + tests | Bajo | `backend/application/inventory/queries/stock_aggregate_query_service.py` |
| **A** | Repunte de **lectores escalares** al adapter, por lotes de 4–6, con tests de equivalencia sembrando `inventory_balances`; delistar cada uno | Bajo–Medio (gated + fallback) | −N lectores del ratchet |
| **B** | Repunte de **lectores agregados** a G1, por lotes; delistar | Medio | −M lectores |
| **C** | **Neutralización de escritores legacy** (quitar `UPDATE productos SET existencia`) una vez confirmado (G0.2) que cada flujo postea canónico; por lotes de 1–3, del más simple (`qr_service`, `lote_service`) al más crítico (`sales_service`) | **Alto** (toca checkout/producción) | −9 escritores |
| **D** | Repunte de `get_product`/`SELECT *` a composición canónica (incl. disponibilidad) | Medio | −3 lectores |
| **E** | **DROP** de `productos` (+ tablas de stock legacy) vía `migrations/deferred/legacy_products_drop.py` bajo env-guard, con allowlist vacía | Irreversible | Corte cerrado |

Orden recomendado: **G0 → G1 → A → B → D → C → E**. (C —neutralizar escritura—
va tarde: sólo cuando todo lector ya es canónico, para minimizar la ventana de
riesgo; y sólo tras confirmar paridad en G0.)

## 5. Mecanismos de seguridad (invariante por lote)

- **Adapter gated + fallback legacy**: repuntar un lector con flag OFF = no-op
  (sigue legacy); el switch a canónico es atómico al prender el flag. → los
  repuntes de lectura son seguros incluso antes de neutralizar escritura, siempre
  que se inyecte el `legacy_available`.
- **Reconciliación por lote** (`drifts()`) antes de considerar un flujo "paritario".
- **Baseline de no-regresión** (node-ids antes/después, 0 fallas nuevas) — mismo
  método que los lotes 1–8.
- **Ratchet monótono**: la allowlist sólo decrece.
- **Reversibilidad**: repuntes de lectura y flip del flag son reversibles;
  neutralización de escritura (C) y DROP (E) son irreversibles → van al final,
  gated.

## 6. Dependencias ya satisfechas

- Backfills de identidad/nombre (148), precio/costo (150), recetas (152),
  rendimientos (153), categorías (166) y `category_id` (167): **hechos**.
- Backfill de stock legacy→canónico + flag ON (134): **hecho**.
- Contexto Inventario canónico (ledger, balances, disponibilidad, reservas,
  reconciliación): **cerrado** (INV-2…INV-27).

## 7. Estimación

- G0: 1 incremento (auditoría + reporte de paridad).
- G1: 1 incremento (servicio agregado + tests).
- A/B/D (lectores, 24+3): ~5–7 lotes acotados.
- C (escritores, 9): ~4–5 lotes, alto escrutinio, `sales_service` al último.
- E: 1 incremento (DROP gated).

## 8. Criterio de terminado

Allowlist del ratchet **vacía**, `PRAGMA foreign_key_check` limpio, reconciliación
sin drift, suite verde, y `legacy_products_drop` ejecutado bajo
`PRODUCTS_ALLOW_LEGACY_DROP=1`. Con eso el maestro `productos` y las tablas de
stock legacy dejan de existir y el corte queda cerrado.
