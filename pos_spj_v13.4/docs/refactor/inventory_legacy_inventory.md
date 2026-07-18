# INV-0.1 — Inventario de legacy de Inventario / Almacenes / Lotes / Trazabilidad

Inventario basado en evidencia (grep/glob del árbol `pos_spj_v13.4/`) del código
actual del dominio Inventario y su clasificación (INV-0). Reemplazo canónico =
bounded context a construir en INV-1…INV-26 (`backend/domain|application|
infrastructure/inventory`, `frontend/desktop/modules/inventory`), siguiendo el
patrón ya establecido para Finance / RRHH / Supplier / Procurement.

Clasificación: **REUSE · MOVE · WRAP_TEMPORARILY · REWRITE · DELETE · BLOCKED**.

> Principio rector: **Inventario no es una columna de existencia; es un ledger
> trazable de movimientos, reservas, balances, lotes, ubicaciones y estados.**

---

## 0. Hallazgo crítico — múltiples fuentes de verdad de existencia

Hoy conviven **cuatro+ fuentes paralelas** de la misma cantidad física, algunas
sincronizadas por triggers (acoplamiento oculto), todas en `float`/`REAL`:

| Fuente | Definición | Identidad | Tipo cantidad | Rol actual | Acción |
|---|---|---|---|---|---|
| `productos.existencia` (`m000_base_schema` L357, `REAL DEFAULT 0`) | Stock denormalizado **dentro del Product Master** | producto (int/uuid) | `REAL` (float) | Se auto-sincroniza desde `inventario_actual` vía `trg_sync_existencia_insert/update` (031) | **DELETE** como fuente canónica (INV-27 §61.4) |
| `inventario_actual` (031, redef. 106) | Balance por `producto+sucursal` | `id TEXT PK` (UUID ✔), `UNIQUE(producto_id,sucursal_id)` | `cantidad REAL`, `costo_promedio REAL` | Balance "vigente" español; alimenta el trigger a `productos.existencia` | **REPLACE** → `InventoryBalance` (Decimal, +warehouse/location/lot/status) |
| `inventory_stock` (098 `canonical_inventory`, backfill 108) | "Canonical single source of truth" (inglés) | uuid | float (salvo `inventory_balance_service` que importa `Decimal`) | Lo leen `backend/application/queries/inventory_balance_service.py` y `inventory_repository`; escrito por `inventory_application_service` | **REUSE/EVOLVE** como semilla del ledger canónico (falta: Decimal estricto, dimensiones lote/ubicación/estado, ledger-first) |
| `branch_inventory` | Stock por sucursal | `int prod_id, int sid` | `float delta` | Mutado por `core/services/inventory/unified_inventory_service.py::_sync_branch_inventory` | **DELETE** con el motor legacy |
| `inventario_diario`, `inventario_global`, `inventario_subproductos`, `inventario_sucursal` | Snapshots/agregados paralelos | mixto | float | Reportes/BI legacy | **DROP** (consolidar en proyecciones del ledger) |

Consecuencia: no existe **un** balance ni **un** ledger; hay proyecciones que se
pisan entre sí y un Product Master contaminado con inventario. INV-3/INV-6
deben dejar **un ledger (`inventory_movements`) + una proyección
(`InventoryBalance`)**, ambos Decimal y born-UUIDv7, y retirar los triggers de
sincronización a `productos.existencia`.

---

## 1. Módulos / UI (PyQt monolítico)

| Archivo | Responsabilidad antigua | Reemplazo canónico | Acción | Consumidores |
|---|---|---|---|---|
| `modulos/inventario_local.py` (~56 KB) | UI + lógica monolítica: existencias, movimientos, ajustes, lotes, alertas, SQL embebido | `frontend/desktop/modules/inventory/` (páginas overview/stock/lots/movements/…) | **BLOCKED** | `interfaz/main_window.py` L36/L640 (`ModuloInventarioLocal`, botón "📦 Inventario"), `core/ui/module_loader.py` L13 (`"inventario"`) |
| `modulos/transferencias.py` (~50 KB) | UI + lógica de transferencias/traspasos entre sucursales | `frontend/desktop/modules/inventory/pages/transfers_page.py` + `transfer_receipts_page.py` | **BLOCKED** | `main_window`/`menu_lateral`/`module_loader` (`"transferencias"`) |
| `core/ui/module_loader.py` L14 `"inventario_enterprise" → modulos.inventario_enterprise` | Alias a módulo enterprise | módulo enterprise real (a crear en INV-25) | **REWRITE** — **entrada MUERTA**: `modulos/inventario_enterprise.py` **no existe** | registry (dead) |
| `core/ui/module_loader.py` L19 `"inv_industrial" → modulos.inventario_industrial` | Inventario industrial | páginas WIP/producción interna del módulo enterprise | **REWRITE** — **entrada MUERTA**: `modulos/inventario_industrial.py` **no existe** | registry (dead) |

> Nota: a diferencia de Compras, **no existe** aún un `inventario_enterprise.py`;
> las entradas del `module_loader` apuntan a módulos inexistentes (fallan silenciosamente al cargar). El módulo enterprise se construye de cero en INV-25.

## 2. Servicios / mutaciones (lógica de negocio)

| Símbolo | Responsabilidad antigua | Reemplazo canónico | Acción | Consumidores |
|---|---|---|---|---|
| `core/services/inventory/unified_inventory_service.py` (~477 líneas) | Motor legacy: `_sync_branch_inventory(c, int prod_id, int sid, float delta)`, mutación directa de stock | `PostInventoryMovementUseCase` + `InventoryBalanceService` (ledger→proyección) | **BLOCKED** | shim `core/services/inventory_engine.py` (`InventoryEngine = UnifiedInventoryService`), consumidores por rastrear (INV-0/§61.15) |
| `core/services/inventory_engine.py` (shim) | Re-export `UnifiedInventoryService as InventoryEngine` | — | **DELETE** con el motor | por rastrear |
| `core/services/inventory_service.py` | Servicio de inventario legacy | UseCases/QueryServices canónicos | **REWRITE/DELETE** | por rastrear |
| `core/services/inventory_availability_service.py` | Disponibilidad legacy | `InventoryAvailabilityQueryService` (domain) | **REWRITE** | Ventas/POS, Forecast |
| `core/services/inventory_balance_service.py` (legacy, junto al de `backend/`) | Balance legacy | `backend/domain/inventory/services/inventory_balance_service.py` | **REWRITE/DELETE** (dup) | por rastrear |
| `core/services/lote_service.py` | Lotes/FIFO legacy | `LotAllocationService` + `InventoryLot` (FEFO por defecto) | **REWRITE** | Producción cárnica, recepción |
| `core/services/stock_reservation_service.py` | Reservas legacy | `ReservationService` + `InventoryReservation`/`InventoryAllocation` | **REWRITE** | Ventas/POS, delivery |
| `core/services/transfer_suggestion_engine.py` | Sugerencias de traslado | `ReplenishmentService` (`ReplenishmentSuggestion`) | **REWRITE** | Planeación |
| `core/services/compras_inventariables_engine.py` | Entrada de compra a inventario | ya cubierto por handlers PUR-13 (evento `PURCHASE_STOCK_ENTRY_REGISTERED`) | **DELETE** (superado) | por rastrear |
| `def registrar_movimiento` (×2, en servicios legacy) | Alta directa de movimiento | `PostInventoryMovementUseCase` (con documento origen + `operation_id`) | **REWRITE** | por rastrear |

> `backend/application/event_handlers/inventory/*` (creados en PUR-13:
> `purchase_stock_entry_handler`, `purchase_lot_entry_handler`,
> `purchase_recipe_explosion_handler`) son **REUSE** — ya event-driven e idempotentes;
> se re-encuadran como handlers del bounded context Inventory en INV-19/INV-20.

## 3. Capa "canónica" parcial ya existente (semilla a evolucionar)

| Archivo | Estado | Acción |
|---|---|---|
| `backend/application/services/inventory_application_service.py` (477 L, "canonical inventory mutations", escribe `inventory_stock`) | Parcial, no ledger-first, float | **MOVE→REWRITE**: base de `PostInventoryMovementUseCase`; falta ledger como fuente, Decimal, lote/ubicación/estado |
| `backend/application/use_cases/register_inventory_movement_use_case.py` (53 L) | Parcial | **REUSE/EVOLVE** → `PostInventoryMovementUseCase` |
| `backend/application/use_cases/{adjust_inventory,get_inventory_stock}_use_case.py` | Parcial | **REUSE/EVOLVE** (ajustes/consulta) |
| `backend/application/queries/inventory_balance_service.py` (303 L, importa `Decimal`, lee `inventory_stock`) | Buen punto de partida | **MOVE** → `domain/inventory/services/` + dimensiones |
| `backend/application/queries/{inventory_query_service,bi_inventory_query_service}.py` | Lecturas UI/BI | **REUSE/EVOLVE** (paginado, DTO) |
| `backend/application/commands/inventory_commands.py` | Commands parciales | **REUSE/EVOLVE** (UUID + Decimal) |
| `backend/infrastructure/db/repositories/inventory_repository.py` (215 L, `inventory_stock`+`inventory_movements`) | Repo canónico parcial | **MOVE** → `infrastructure/db/repositories/inventory/` + UoW atómico (movimiento+balance+lote+reserva+evento+outbox) |
| `repositories/inventory_repository.py` (legacy) | Repo legacy | **DELETE** tras migrar consumidores |
| `repositories/transferencias.py` | Repo transferencias legacy | **DELETE** → `transfer_repository` canónico |
| `api/routers/inventario.py` | Router API legacy | **REWRITE** sobre UseCases/QueryServices |
| `core/use_cases/inventario.py` | UC legacy (CQRS temprano) | **REWRITE/DELETE** |

## 4. Esquema — tablas a consolidar (INV-3 / §61.10)

| Tabla | Rol | Acción |
|---|---|---|
| `productos.existencia` (columna) | stock en Product Master | **DROP columna** como fuente (retirar triggers `trg_sync_existencia_*`) |
| `inventario_actual` | balance ES (UUID PK, float) | **REPLACE** → `InventoryBalance` (Decimal) |
| `inventory_stock` | balance EN (semilla) | **EVOLVE** → proyección del ledger |
| `branch_inventory` | stock por sucursal (int, float) | **DROP** |
| `inventario_diario` / `inventario_global` / `inventario_subproductos` / `inventario_sucursal` | snapshots/agregados | **DROP** (proyecciones/BI del ledger) |
| `movimientos_inventario` (105) | kardex ES | **MERGE** → `inventory_movements` (ledger único, +líneas, lote, ubicación, estado, documento origen) |
| `inventory_movements` (098) | ledger EN | **EVOLVE** (ledger canónico) |
| `movimientos_lote` | movimientos de lote | **MERGE** en líneas del ledger + `inventory_lot` |
| `movimientos_trazabilidad` | trazabilidad QR | **MERGE** → `traceability_link` |
| `lotes` | lotes | **REPLACE** → `inventory_lot` (Decimal, origen, caducidad, calidad) |
| `transferencias` / `transferencias_inventario` / `traspasos` | **3 tablas de transferencia** | **MERGE → 1**: `inventory_transfer` (+`transfer_shipment`/`transfer_receipt`) |
| `recepciones` | recepciones genéricas | **REPLACE** → `transfer_receipt` / evento `GoodsReceipt` (según origen) |
| `ajustes_inventario` | ajustes | **REPLACE** → `inventory_adjustment` (+líneas, motivo, autorización) |
| `stock_reservas` / `stock_reserva_detalles` | reservas | **REPLACE** → `inventory_reservation`/`inventory_allocation` |
| `inventory_reservations` (098) | reservas EN | **EVOLVE** |
| (no existen) conteos / cuarentena / ubicaciones / almacenes / cadena de frío | — | **CREATE** (INV-5/9/13/15) |

> Doble ledger (`movimientos_inventario` ES + `inventory_movements` EN), doble
> balance (`inventario_actual` + `inventory_stock`) y triple transferencia son la
> deuda estructural central. INV-3/INV-6/INV-12 la colapsan.

## 5. Fuente por usuario y existencia en Producto

- `inventario_usuarios` como **tabla** no se encontró en el esquema base/standalone
  (grep sin match en `migrations/` + `backend/infrastructure/db`). Se mantiene como
  **verificación INV-0/§61.5**: rastrear referencias en runtime; si representa
  custodia por usuario, migrar a `warehouse`/`location`/`assignment`, nunca usar
  usuarios como almacenes implícitos. (Sin evidencia de tabla ⇒ probable ausente.)
- `productos.existencia` **sí** existe y es fuente canónica de facto vía triggers ⇒
  **DELETE** como fuente (guardrail `test_product_master_does_not_store_inventory.py`).

## 6. SQL en UI / mutaciones directas (§61.6 / §61.7)

- Monolitos `inventario_local.py` (56 KB) y `transferencias.py` (50 KB): SQL
  embebido, `commit()`/`rollback()` en UI (a confirmar por conteo en INV-25/27).
- Mutación directa canónica hallada: `_sync_branch_inventory` (float) +
  `registrar_movimiento` (×2). Sustituir por `PostInventoryMovement` /
  `ReverseInventoryMovement`. No se hallaron `actualizar_stock/sumar_stock/
  restar_stock/set_existencia` como `def` (posible presencia inline en monolitos —
  reconfirmar durante INV-25/27 con grep sobre cuerpos).

## 7. Permisos, eventos y notificaciones legacy

- **Permisos** (§61.11): rastrear `INVENTARIO`, `ADMIN_INVENTARIO`,
  `PUEDE_AJUSTAR_STOCK`, `PUEDE_TRANSFERIR` → migrar a los ~70 permisos granulares
  `INVENTORY_*` (INV-1). Guardrail `test_inventory_does_not_use_legacy_permissions.py`.
- **Eventos** (§61.12): `STOCK_ACTUALIZADO`, `INVENTARIO_CAMBIADO`,
  `TRASPASO_REALIZADO`, `RECEPCION_COMPLETADA` → vocabulario canónico
  `INVENTORY_MOVEMENT_POSTED`, `INVENTORY_TRANSFER_*`, etc. (post-commit, con
  `event_id/operation_id/entity_id` distintos).
- **Notificaciones/WhatsApp** (§43/§44): centralizar en `InventoryNotificationGateway`
  (policy-driven), nunca envío directo desde UI.

## 8. Reglas de negocio válidas a PRESERVAR (PRIORIDAD 0)

Se extraen y re-implementan (no se pierden) sobre la arquitectura canónica:

- Costo promedio ponderado en entrada (hoy en `inventario_actual.costo_promedio` +
  handler `purchase_stock_entry_handler`).
- Lotes de peso variable cárnico + FIFO/FEFO (`purchase_lot_entry_handler`,
  `lote_service`).
- Explosión de recetas al consumir (`purchase_recipe_explosion_handler`,
  `recipe_engine`).
- Reservas de stock para ventas/delivery (`stock_reservation_service`).
- Sugerencias de reabasto/transferencia (`transfer_suggestion_engine`).
- Alertas de stock mínimo (`alert_engine`, `alerta_stock_minimo` en 031).
- Disponibilidad para POS (`inventory_availability_service`).

Cada una requiere **tests de caracterización** antes de mover (regla 4 del skill).

---

## Tabla resumen de mapeo (extracto para el reporte final §66)

| Elemento anterior | Destino canónico | Acción | Consumidores restantes |
|---|---|---|---|
| `productos.existencia` | `InventoryBalance` | DELETE (fuente) | por rastrear |
| `inventario_actual` | `InventoryBalance` (Decimal) | REPLACE | por rastrear |
| `inventory_stock` | proyección del ledger | EVOLVE | activo (canónico parcial) |
| `branch_inventory` | `InventoryBalance` | DELETE | `unified_inventory_service` |
| `movimientos_inventario` + `inventory_movements` | ledger único `inventory_movements` | MERGE | por rastrear |
| `transferencias`+`transferencias_inventario`+`traspasos` | `InventoryTransfer` | MERGE→1 | monolito transferencias |
| `ajustes_inventario` | `InventoryAdjustment` | REPLACE | monolito inventario |
| `stock_reservas`(+detalles) | `InventoryReservation`/`Allocation` | REPLACE | reservation service |
| `lotes` | `InventoryLot` | REPLACE | lote_service |
| `unified_inventory_service` (float, int ids) | `PostInventoryMovement` | DELETE | shim `inventory_engine` |
| `registrar_movimiento()` | `PostInventoryMovement` | REWRITE | por rastrear |
| `modulos/inventario_local.py` | `frontend/.../inventory/` | DELETE (tras cero consumidores) | main_window, module_loader |
| `modulos/transferencias.py` | `.../inventory/pages/transfers_page.py` | DELETE (tras cero consumidores) | main_window, module_loader |
| permiso `INVENTARIO` | permisos `INVENTORY_*` granulares | DELETE | por rastrear |
| WhatsApp/alertas directas | `InventoryNotificationGateway` | DELETE | por rastrear |
