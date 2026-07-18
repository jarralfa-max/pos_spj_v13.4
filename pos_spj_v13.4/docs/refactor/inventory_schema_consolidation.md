# INV-3 — Consolidación del esquema de Inventario

Plan de consolidación de las tablas de inventario: el estado legacy tiene **4+
fuentes de existencia**, **doble ledger** y **triple transferencia** (ver
`inventory_legacy_inventory.md`). El bounded context canónico (INV-3) introduce
**un ledger + una proyección** born-clean (UUIDv7, Decimal), que **coexiste** con
lo legacy hasta que INV-6/INV-11 repunten los lectores e INV-27 ejecute el DROP.

## Esquema canónico creado (migración 121, `inventory_schema.py`)

| Tabla canónica | Rol | Notas |
|---|---|---|
| `inventory_ledger` | Ledger de movimientos (fuente de verdad, §9/§15) | `operation_id` UNIQUE (idempotencia); documento origen obligatorio |
| `inventory_ledger_lines` | Líneas del movimiento | `quantity`/`weight`/`unit_cost` TEXT decimal; lote/ubicación/estado |
| `inventory_balances` | Proyección del ledger (§14) | UNIQUE por dimensión completa; `''` en location/lot/serial ausentes |
| `warehouses` / `warehouse_zones` / `storage_locations` | Almacenes/zonas/ubicaciones (§12) | jerarquía vía `parent_location_id` |
| `inventory_operation_limits` | Límites configurables (§48) | scope user/role/branch/warehouse × operation_kind |
| `inventory_settings` | Configuración por scope (§56) | key/value con vigencia y versión |
| `inventory_authorization_log` | Autorizaciones en caliente (§48) | grant auditable |
| `inventory_audit_log` | Auditoría (§49) | antes/después, responsable, operation_id |
| `inventory_outbox` / `inventory_processed_events` | Outbox transaccional + idempotencia de eventos (§58/§59) | |

### Nombres y colisiones

- El nombre `inventory_movements` **ya pertenece** a la migración legacy 098
  (`canonical_inventory`) y tiene lectores vivos
  (`backend/infrastructure/db/repositories/inventory_repository.py`). Por eso el
  ledger canónico se llama **`inventory_ledger`** durante la coexistencia; el
  nombre `inventory_movements` se **reclama en INV-27** tras el DROP legacy.
- El resto de nombres canónicos (`warehouses`, `storage_locations`,
  `inventory_balances`, …) **no colisionan** (verificado por grep sobre
  `migrations/` + `schema/`).

## Mapa de consolidación (legacy → canónico)

| Tabla legacy | Fuente | Acción | Fase de corte |
|---|---|---|---|
| `productos.existencia` (columna, trigger-sync) | m000 + 031 | Dejar de ser fuente; retirar `trg_sync_existencia_*` | INV-6 (repunte lectores) → INV-27 (drop columna/trigger) |
| `inventario_actual` (UUID PK, float) | 031/106 | Reemplazar por `inventory_balances` (Decimal) | INV-6 → INV-27 |
| `inventory_stock` (098) | 098/108 | Colapsar en `inventory_balances` (proyección) | INV-6 → INV-27 |
| `branch_inventory` (int, float) | legacy | DROP | INV-27 |
| `inventario_diario`/`global`/`subproductos`/`sucursal` | varios | DROP (proyecciones/BI del ledger) | INV-27 |
| `inventory_movements` (098) | 098 | Colapsar en `inventory_ledger`; reclamar nombre | INV-6 → INV-27 |
| `movimientos_inventario` (105) | 105 | Colapsar en `inventory_ledger` | INV-6 → INV-27 |
| `movimientos_lote` / `movimientos_trazabilidad` | legacy | Colapsar en líneas del ledger + `inventory_lot`/`traceability_link` | INV-7/INV-17 → INV-27 |
| `transferencias` + `transferencias_inventario` + `traspasos` | 031/legacy | **MERGE → 1** `inventory_transfer` (+shipment/receipt) | INV-12 → INV-27 |
| `recepciones` | legacy | `transfer_receipt` / evento GoodsReceipt según origen | INV-12/INV-19 → INV-27 |
| `ajustes_inventario` | legacy | `inventory_adjustment` (+líneas) | INV-14 → INV-27 |
| `stock_reservas` (+detalles) / `inventory_reservations`(098) | legacy/098 | `inventory_reservation`/`inventory_allocation` | INV-10 → INV-27 |
| `lotes` | legacy | `inventory_lot` (Decimal, origen, caducidad, calidad) | INV-7 → INV-27 |

## Tablas canónicas pendientes (se crean en su fase, no en INV-3)

Para evitar columnas especulativas, las tablas de lotes, reservas, transferencias,
conteos, ajustes, cuarentena, series, trazabilidad y cadena de frío se añaden en
su fase (INV-7/10/12/13/14/15/17/9) junto a sus entidades, ampliando
`inventory_schema.py` y con su propia migración. INV-3 fija sólo el núcleo:
ledger, balance, almacenes/ubicaciones, límites, settings, auth/audit, outbox.

## Riesgos del corte

- **Triggers `trg_sync_existencia_*`**: retirarlos rompe lectores de
  `productos.existencia` (POS/BI). Orden: repuntar lectores a
  `InventoryBalanceService` (INV-6/INV-11) → retirar trigger → drop columna.
- **Doble escritura durante coexistencia**: legacy escribe
  `inventario_actual`/`inventory_stock`; canónico escribe `inventory_ledger`→
  `inventory_balances`. Hasta INV-6 no hay reconciliación automática; el corte
  define que POS/Compras/Producción escriban **sólo** vía eventos al ledger.
- **Bug preexistente `trg_recalc_inventario_actual`** (`inventario_actual.id NOT
  NULL` sin generar id): se elimina al reemplazar la proyección (INV-6).
