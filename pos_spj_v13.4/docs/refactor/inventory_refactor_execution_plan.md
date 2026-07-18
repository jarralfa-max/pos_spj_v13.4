# INV-0 — Plan de ejecución del refactor de Inventario (Inventory bounded context)

Plan por fases (INV-0 → INV-28) para construir el bounded context canónico de
**Inventario / Almacenes / Ledger / Lotes / Trazabilidad / Peso variable /
Cadena de frío**, siguiendo la REGLA CERO (UUIDv7), Decimal-only, ledger-based,
event-driven, offline-first, security-first y el Design System JUANIS.

Reemplazo canónico = `backend/domain|application|infrastructure/inventory` +
`frontend/desktop/modules/inventory`, mismo patrón que Finance / RRHH / Supplier /
Procurement (ya migrados).

**Regla de avance:** no se avanza de fase si los tests de la fase actual no pasan.
**Regla de no-regresión:** cada fase mide node-ids de tests antes/después (0 nuevas
fallas), como en PUR-13.

---

## Estado del árbol (hallazgos INV-0, ver `inventory_legacy_inventory.md`)

- **4+ fuentes de existencia** en float, algunas acopladas por trigger:
  `productos.existencia` ↔ `inventario_actual` ↔ `inventory_stock` ↔ `branch_inventory`
  (+ `inventario_diario/global/subproductos/sucursal`).
- **Doble ledger**: `movimientos_inventario` (ES) + `inventory_movements` (EN).
- **Triple transferencia**: `transferencias` + `transferencias_inventario` + `traspasos`.
- **Semilla canónica parcial** (reutilizable): `backend/application/{services,use_cases,
  queries,commands}/inventory_*` + `backend/infrastructure/db/repositories/inventory_repository.py`
  (escriben/leen `inventory_stock`/`inventory_movements`) — falta ledger-first,
  Decimal estricto, dimensiones lote/ubicación/estado, y encuadre en bounded context.
- **No existe** `backend/domain/inventory/` ni `frontend/desktop/modules/inventory/`
  ni un módulo enterprise (las entradas `inventario_enterprise`/`inv_industrial` del
  `module_loader` apuntan a archivos inexistentes).
- **Handlers ya event-driven** (PUR-13): `purchase_stock_entry/lot_entry/recipe_explosion`
  — REUSE.

## Estrategia de corte

Igual que Compras: construir el contexto canónico **en paralelo**, migrar por
eventos, verificar cero consumidores, y sólo entonces borrar legacy (sin wrapper
permanente). El punto de partida NO es un vacío: `inventory_stock`/`inventory_movements`
y su repo/servicios se **evolucionan** hacia ledger-first + Decimal + dimensiones,
en vez de crear una quinta tabla.

Decisión clave de esquema (a validar en INV-3): **un** ledger `inventory_movements`
(fuente de verdad) + **una** proyección `InventoryBalance`; retirar triggers de
sync a `productos.existencia`; colapsar los 3 transfers y los 2 kardex.

---

## Fases

| Fase | Objetivo | Entregable principal | Estado |
|---|---|---|---|
| **INV-0** | Auditoría + plan | `inventory_legacy_inventory.md`, este plan | ✅ |
| **INV-1** | Seguridad: 67 permisos `INVENTORY_*` granulares, alcance sucursal/almacén, límites (WITHIN/REQUIRES_APPROVAL/EXCEEDS), segregación de funciones, autorización en caliente (grant auditado), permission gate | `backend/{domain,application}/inventory/**` + tests (36) | ✅ |
| **INV-2** | Dominio base: `Warehouse`/`WarehouseZone`/`StorageLocation`, 13 `InventoryStatus`, 25 `MovementType`+dirección, `InventoryMovement(+Line)` (ledger), `InventoryBalance` (proyección, disponible=on-hand−reservado), `Quantity`/`Weight` VOs, policies `NegativeInventory`+`MovementValidation`, 34 eventos canónicos + `build_event_payload`, enums | `backend/domain/inventory/**` + tests (33) | ✅ |
| **INV-3** | Esquema born-clean UUIDv7+Decimal: `inventory_schema.py` (12 tablas: ledger `inventory_ledger`+lines, `inventory_balances`, almacenes/zonas/ubicaciones, límites, settings, auth/audit, outbox), constraints/índices, migración 121, bootstrap; plan de consolidación | `inventory_schema.py` + migración 121 + `inventory_schema_consolidation.md` + tests (9) | ✅ |
| **INV-4** | Repositorios + `InventoryUnitOfWork` atómico (ledger+balance+almacenes+límites+settings+auth+audit+outbox+processed en una transacción; commit al salir limpio, rollback ante excepción) | `infrastructure/db/repositories/inventory/**` + tests (10) | ✅ |
| INV-5 | Almacenes, zonas, ubicaciones, jerarquía, estados + UI | páginas warehouses/locations | ⏳ |
| **INV-6** | **Ledger y balances**: `PostInventoryMovementUseCase` (única ruta de escritura de stock; idempotente por operation_id; proyección de balance por dirección con NegativeInventoryPolicy; ledger+balance+audit+outbox atómicos) + `ReverseInventoryMovementUseCase` (inverso exacto, un solo reverso) + `InventoryProjectionService` | `backend/application/inventory/**` + tests (12) | ✅ |
| INV-7 | Lotes y caducidad (FEFO por defecto), alertas de vencimiento | `InventoryLot` + `expiry_risk_service` | ⏳ |
| INV-8 | Peso variable (piezas + peso), báscula vía gateway, rangos, captura manual autorizada | `CatchWeightPosition` + `scale_gateway` | ⏳ |
| INV-9 | Cadena de frío: temperatura, sensores, excursiones, bloqueo, alertas | `cold_chain_policy` + lecturas | ⏳ |
| INV-10 | Reservas y asignaciones (vigencia, lotes, liberación, idempotencia) | `ReservationService` | ⏳ |
| INV-11 | Integración Ventas/POS: disponibilidad, reservas, salidas, reversos, devoluciones (e2e) | `InventoryAvailabilityQueryService` + handlers | ⏳ |
| INV-12 | **Transferencias** canónicas (1 agregado): solicitud→aprobación→reserva→picking→despacho→tránsito→recepción→diferencias | `InventoryTransfer`/`Shipment`/`Receipt` | ⏳ |
| INV-13 | Conteos (ciego, reconteo, por peso/piezas/lote/ubicación, diferencias, aprobación) | `InventoryCount(+Line)` | ⏳ |
| INV-14 | Ajustes (motivos, autorización, posteo, reverso, auditoría) | `InventoryAdjustment(+Line)` | ⏳ |
| INV-15 | Calidad y cuarentena (bloqueo, cuarentena, liberación, rechazo, disposición) | `InventoryQuarantine`/`QualityHold` | ⏳ |
| INV-16 | Mermas/desperdicios/decomisos clasificados + integración financiera (evento) | movimientos WASTE/SHRINKAGE/… | ⏳ |
| INV-17 | Trazabilidad ascendente/descendente + preparación recalls | `TraceabilityLink` + query service | ⏳ |
| INV-18 | Reposición (mín/máx/safety/target, sugerencias compra vs transferencia) | `ReplenishmentRule`/`Suggestion` | ⏳ |
| INV-19 | Integración Compras (recepciones/calidad/devoluciones/cost reference) — **reencuadra** handlers PUR-13 | event handlers inventory | ⏳ |
| INV-20 | Integración Producción (consumos/outputs/coproductos/subproductos/merma/WIP) | event handlers | ⏳ |
| INV-21 | Preparación Sacrificio (eventos futuros, lotes, canales, outputs, contratos) | handlers/contracts stub | ⏳ |
| INV-22 | Offline-first: ledger local, outbox, secuencia, sync, reintentos, conflictos | sync + idempotencia | ⏳ |
| INV-23 | Notificaciones + WhatsApp (policies, alertas, destinatarios, canales, idempotencia, auditoría) | `InventoryNotificationGateway` | ⏳ |
| INV-24 | BI/analytics (QueryServices, KPI, charts, frescura, export) | query services | ⏳ |
| INV-25 | UI/UX enterprise (navegación, páginas, diálogos, tema JUANIS, estados, tooltips, responsive) | `frontend/desktop/modules/inventory/**` | ⏳ |
| INV-26 | Impresión/etiquetas (lote, peso, transferencias, conteos, reimpresión, auditoría) | renderers + print gateway | ⏳ |
| INV-27 | **Eliminación de legacy**: migrar funcional, borrar monolitos, `productos.existencia`, consolidar tablas/transferencias, imports, vaciar allowlist, reporte | `inventory_legacy_removal_report.md` | ⏳ |
| INV-28 | Validación final: suites dominio/aplicación/integración/e2e/seguridad/UI/arquitectura + bootstrap limpio + auditorías | `module_relocation_map.md` → `MIGRATED` | ⏳ |

## Guardrails de arquitectura (a crear conforme avanza)

`test_inventory_ui_uses_query_services.py`, `..._uses_use_cases.py`,
`..._has_no_database_access.py`, `..._has_no_inline_styles.py`,
`..._has_no_hardcoded_colors.py`, `..._uses_standard_components.py`,
`..._uses_decimal.py`, `..._uses_uuidv7.py`, `..._is_ledger_based.py`,
`test_product_master_does_not_store_inventory.py`,
`test_inventory_modules_do_not_update_stock_directly.py`,
`test_{sales,purchases,production}_does_not_write_inventory_tables.py`,
`test_inventory_transfers_are_canonical.py`,
`test_inventory_permissions_are_granular.py`,
`test_inventory_notifications_use_gateway.py`,
`test_inventory_whatsapp_uses_gateway.py`,
`test_inventory_events_are_post_commit.py`,
`test_no_legacy_inventory_imports.py`,
`test_inventory_legacy_allowlist_is_empty.py`.

## Riesgos / dependencias

- **Alto acoplamiento por triggers** (`productos.existencia`): retirarlos puede
  romper lecturas de POS/BI que leen la columna. Mitigación: primero repuntar
  lectores a `InventoryBalanceService`, luego retirar trigger (INV-6/INV-11).
- **Doble ledger/balance activo**: `inventory_stock` ya es escrito por la semilla
  canónica y `inventario_actual` por el legacy; durante la transición ambos deben
  converger vía el ledger antes del DROP (INV-3 define orden de corte).
- **Trigger `trg_recalc_inventario_actual`** tiene un bug preexistente
  (`inventario_actual.id NOT NULL` sin generar id en algunos INSERT) — se resuelve
  al reemplazar la proyección por `InventoryBalance` (INV-3/INV-6).
- **POS/Producción cárnica** leen `inventory_balance_service` (backend) — coordinar
  su repunte al servicio de dominio para no duplicar.
- Volumen: 28 fases; cada una es un lote funcional con tests. Se ejecuta de forma
  incremental, dirigida por fase (como PUR/RRHH/SUP).

## Siguiente paso recomendado

**INV-1 (Seguridad y permisos)** como cimiento — igual que en PUR-2/SUP/RRHH,
la seguridad granular precede al dominio para que cada UseCase nazca revalidando
autorización. Alternativa válida: **INV-2 (Dominio base)** si se prefiere fijar
primero las entidades/estados/eventos. Ambas no dependen de decisiones de negocio
adicionales; el resto encadena tras INV-3 (esquema).
