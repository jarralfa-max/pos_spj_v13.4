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
| **INV-5** | Almacenes/zonas/ubicaciones (§12): use cases `CreateWarehouse`/`SetWarehouseStatus` (activar/bloquear), `CreateZone`, `CreateLocation` (jerarquía vía `parent_location_id`, valida padre), `SetLocationStatus` — permisos granulares `WAREHOUSE_*`/`LOCATION_MANAGE`, idempotentes por código, auditoría + eventos canónicos; `WarehouseQueryService` (listas + `location_hierarchy` en árbol); UI: view-models (mapeos es-MX tipo/estado + `warehouses_table`/`locations_table` con indentación), métodos de presenter, 2 entradas de navegación (`WAREHOUSE_VIEW`/`LOCATION_VIEW`) y páginas PyQt5 `WarehousesPage`/`LocationsPage` | `backend/application/**` + `frontend/**` + tests (14) | ✅ |
| **INV-6** | **Ledger y balances**: `PostInventoryMovementUseCase` (única ruta de escritura de stock; idempotente por operation_id; proyección de balance por dirección con NegativeInventoryPolicy; ledger+balance+audit+outbox atómicos) + `ReverseInventoryMovementUseCase` (inverso exacto, un solo reverso) + `InventoryProjectionService` | `backend/application/inventory/**` + tests (12) | ✅ |
| **INV-7** | Lotes y caducidad: `InventoryLot` (origen, códigos proveedor/producción/sacrificio, calidad), tabla `inventory_lots` (migración 122), `LotAllocationService` (FEFO por defecto, FIFO/LIFO/MANUAL; salta vencidos/bloqueados/sin vida útil), `ExpiryRiskService` (OK/WARNING/CRITICAL/EXPIRED), repo + UoW, use cases Register/SetQuality | `backend/domain|application/inventory/**` + tests (23) | ✅ |
| **INV-8** | Peso variable: VOs `WeightReading` (bruto/tara/neto/estabilidad/origen) y `CatchWeightPosition` (piezas+peso), `CatchWeightPolicy` (estable para auto, rango, tolerancia de promedio, manual fuera de rango → autorización), `ScaleGateway` (Stub/Manual), `WeightCaptureService` (scale + manual con override autorizado) | `backend/domain|application|infrastructure/**` + tests (18) | ✅ |
| **INV-9** | Cadena de frío: `ColdChainRange` VO, entidades `TemperatureReading`/`TemperatureExcursion`, `ColdChainPolicy` (COMPLIANT/WARNING/OUT_OF_RANGE + acción NONE/WARN/QUARANTINE), tablas + migración 123, `ColdChainRepository`, `RecordTemperatureReadingUseCase` (excursión → alerta; auto-block → cuarentena de lote) | `backend/**` + tests (16) | ✅ |
| **INV-10** | Reservas y asignaciones: `InventoryReservation`/`InventoryAllocation`, tablas `inventory_reservation`/`inventory_allocation` (migración 124), use cases Create (reduce disponibilidad sin mover físico, idempotente) / Release (restaura disponibilidad, idempotente) / Allocate (asigna lotes FEFO) | `backend/**` + tests (10) | ✅ |
| **INV-11** | Integración Ventas/POS: `InventoryAvailabilityQueryService` (available = on-hand−reservado, por estado), handlers `SaleIssueHandler` (SALE_ISSUE) y `CustomerReturnHandler` (SALE_RETURN → PENDING_INSPECTION), guardrail `test_sales_does_not_write_inventory_tables`. Listos para el cutover INV-27 (no live-wired para evitar doble descuento) | `backend/application/**` + tests (9) | ✅ |
| **INV-12** | **Transferencias** canónicas (1 agregado que colapsa las 3 tablas legacy): `InventoryTransfer(+Line)` con máquina de estados (draft→pending→approved→picking→ready→in_transit→received/with_differences/closed), tablas + migración 125, use cases Create/Approve/Dispatch/Receive. §24: despacho baja origen (TRANSFER_DISPATCH) y destino no sube hasta recibir (TRANSFER_RECEIPT); diferencias SHORT/OVER; segregación despachador≠receptor; movimiento+estado atómicos vía `post_movement` | `backend/**` + tests (14) | ✅ |
| **INV-13** | Conteos: `InventoryCount(+Line)` con máquina de estados, conteo **ciego** (esperado no expuesto en captura), bloqueo al confirmar, cálculo de varianza, reconteo, tablas + migración 126, use cases Create(snapshot de esperado)/Record/Confirm(→VARIANCE_DETECTED)/Approve (segregación contador≠aprobador de varianza crítica) | `backend/**` + tests (12) | ✅ |
| **INV-14** | Ajustes: `InventoryAdjustment(+Line)` con motivos configurables + deltas firmados, tablas + migración 127, use cases Create (evalúa límite → WITHIN/REQUIRES_APPROVAL), Approve (segregación creador≠aprobador + grant auditado), Post (ADJUSTMENT_IN/OUT al ledger, idempotente), Reverse (inverso), y CreateFromCount (varianza aprobada → ajuste) que cierra el lazo del conteo | `backend/**` + tests (9) | ✅ |
| **INV-15** | Calidad y cuarentena: `InventoryQuarantine` (motivos, estados open→under_review→released/rejected/disposed), tabla + migración 128, use cases Quarantine (AVAILABLE→QUARANTINED vía STATUS_TRANSFER, sale de disponible), Release (QUARANTINED→AVAILABLE, segregación bloqueador≠liberador), Dispose (salida de cuarentena, permiso DISPOSAL_AUTHORIZE) | `backend/**` + tests (6) | ✅ |
| **INV-16** | Mermas/desperdicios/decomisos clasificados (9 `WasteType`), mapeo a movimiento físico (WASTE/SHRINKAGE/EXPIRY_DISPOSAL), tabla `inventory_waste_event` + migración 129, `RegisterWasteUseCase` (teórica sin movimiento; disposición requiere DISPOSAL_AUTHORIZE; evento `INVENTORY_WASTE_RECORDED` → Finanzas para valuación) | `backend/**` + tests (5) | ✅ |
| **INV-17** | Trazabilidad ascendente (origen/proveedor/recepción) y descendente (venta/transferencia/consumo) derivada del ledger por lote + genealogía explícita (`TraceabilityLink` para saltos de identidad de lote: producción/faena/reempaque), tabla `inventory_traceability_link` + migración 130, `TraceabilityQueryService` (`trace_upstream`/`trace_downstream`/`recall_report` con recorrido recursivo de genealogía) + `RegisterTraceabilityLinkUseCase` (idempotente, evento `INVENTORY_TRACEABILITY_LINKED`), permiso `TRACEABILITY_LINK`, preparado para recalls | `backend/**` + tests (11) | ✅ |
| **INV-18** | Reposición born-clean (REWRITE del `transfer_suggestion_engine` legacy int/float): entidades `ReplenishmentRule` (mín/reorder/target/máx/safety/lead-time/fuente preferida) y `ReplenishmentSuggestion` (Decimal, UUIDv7), `ReplenishmentPolicy` puro (dispara ≤ reorder, repone hasta target, urgencia STOCKOUT/CRITICAL/REORDER, decide **compra vs transferencia** según excedente del almacén origen), tablas `inventory_replenishment_rule`/`_suggestion` + migración 131, `SetReplenishmentRuleUseCase` (upsert) + `GenerateReplenishmentSuggestionsUseCase` (idempotente por corrida, evento `INVENTORY_REPLENISHMENT_SUGGESTED`; sólo planea, no mueve stock) + `ReplenishmentQueryService`, permisos `REPLENISHMENT_VIEW/MANAGE/GENERATE` | `backend/**` + tests (19) | ✅ |
| **INV-19** | Integración Compras canónica (reencuadre de los handlers PUR-13 sobre el ledger born-clean): `PurchaseReceiptHandler`/`DirectPurchaseReceiptHandler` (GOODS_RECEIPT_COMPLETED / DIRECT_PURCHASE_RECEIVED → PURCHASE_RECEIPT con **cost reference** en la línea del ledger para Finanzas, **calidad** a bucket PENDING_INSPECTION/QUARANTINED, y creación+enlace idempotente de **lote** canónico PURCHASE), `SupplierReturnHandler` (PURCHASE_RETURN_CREATED → SUPPLIER_RETURN) y `GoodsReceiptReversedHandler` (GOODS_RECEIPT_REVERSED → reverso del movimiento por documento). Todos idempotentes por operation_id, contexto **paralelo** no cableado al bus hasta INV-27 (evita doble conteo con legacy) | event handlers inventory + tests (7) | ✅ |
| **INV-20** | Integración Producción canónica (REWRITE del `ProductionInventoryHandler` legacy float): `ProductionExecutionHandler` consume PRODUCTION_COMPLETED y postea **PRODUCTION_CONSUMPTION** (insumos) + **PRODUCTION_OUTPUT** (producto terminado + **coproductos/subproductos** clasificados por `output_type`), crea+enlaza lotes de output (origen PRODUCTION) con **genealogía** PRODUCTION insumo→output (recall raw→terminado), **merma implícita** en el ledger (consumo − output, sin movimiento fantasma), **WIP** a bucket PRODUCTION_HOLD no vendible; idempotente por operation_id, contexto paralelo no cableado hasta INV-27 | event handlers inventory + tests (4) | ✅ |
| **INV-21** | Preparación Sacrificio/Faena (FUTURO, §33) — **stub sin esquema ni cableado vivo**: paquete `domain/inventory/slaughter/` con vocabulario (`SlaughterSpecies`/`CarcassState`/`SlaughterOutputType`), contratos inmutables Decimal (`SlaughterOrderContract`/`CarcassContract`/`SlaughterOutputContract`), `SlaughterEvents` (contrato de eventos futuros, fuera de `ALL_INVENTORY_EVENTS`) y `SlaughterPlanningService` puro que mapea la faena sobre las primitivas born-clean ya existentes (`SLAUGHTER_INPUT/OUTPUT_FUTURE`, `LotOrigin.SLAUGHTER_FUTURE`, genealogía `SLAUGHTER`): ganado→canal→cortes, WASTE nunca es stock; `SlaughterExecutedStubHandler` como costura de suscripción no-op (`SLAUGHTER_ENABLED=False`) | `backend/**` + tests (9) | ✅ |
| **INV-22** | Offline-first sobre el outbox transaccional (§57): tablas `inventory_sync_dispatch` (secuencia monotónica por nodo + reintentos/backoff + dead-letter) y `inventory_sync_cursor` (progreso por nodo/stream) + migración 132; `RetryPolicy` puro (backoff exponencial con tope); `InventoryOutboxDispatcher` (`register_pending` asigna secuencia local; `dispatch_due` despacha en orden vía `SyncTransport`, reintenta con backoff, dead-letter tras el tope, y avanza el cursor sólo hasta la última secuencia contigua sincronizada — preserva orden entre reconexiones); `InventoryEventIngestor` (aplicación entrante idempotente por `event_id` = resolución de duplicados/conflictos). Todo dentro del UoW atómico | `backend/**` + tests (12) | ✅ |
| **INV-23** | Notificaciones + WhatsApp (§55): enums (canal/severidad/tipo-destinatario/status + `ALERT_EVENT_SEVERITY`), entidad `NotificationRule`, tablas `inventory_notification_rule` (ruteo evento→destinatario/canal/severidad + throttle) y `inventory_notification_log` (auditoría + idempotencia por `dedupe_key` UNIQUE + fuente de throttle) + migración 133; `InventoryNotificationGateway` (Protocol port + `InMemoryNotificationGateway`); `InventoryNotificationService.notify` (deriva severidad, matchea reglas en alcance, **gate por severidad mínima**, **idempotente por event_id**, **throttle por ventana**, entrega vía gateway, audita cada resultado SENT/FAILED/THROTTLED/SUPPRESSED, emite `INVENTORY_NOTIFICATION_CREATED` + `INVENTORY_WHATSAPP_ALERT_SENT`); `SetNotificationRuleUseCase` (permisos `NOTIFICATIONS_MANAGE`/`WHATSAPP_ALERTS_MANAGE`) | `backend/**` + tests (7) | ✅ |
| **INV-24** | BI/analytics de Inventario (§55, read-only): `InventoryAnalyticsService` produce KPIs (`InventoryKpiDTO`: disponible/reservado/cuarentena/reposición abierta/crítica, math en Decimal, valor string), `ChartDataDTO` color-free (donut existencia por estado, barras por almacén/tipo de movimiento/merma), señal de frescura (`DataFreshnessDTO` LIVE/FRESH/DELAYED/STALE desde el último `occurred_at` del ledger) y export CSV de disponibilidad; helper `to_chart_number` (único cruce Decimal→float, fuera del contexto para mantenerlo Decimal-only). UI: métodos de presenter + `InventoryAnalyticsPage` (KPIBar + `HtmlChartView` con degradación a tabla + exportar) + navegación (`INVENTORY_EXPORT`) | `backend/application/inventory/analytics/**` + `frontend/**` + tests (10) | ✅ |
| **INV-25** | UI/UX enterprise de Inventario (`frontend/desktop/modules/inventory/**`, patrón presenter/view-model como Compras): `view_models` (mapeos es-MX de estado/urgencia/fuente/severidad + formatters Decimal-safe + `TableViewModel`/`KpiViewModel`), `presenter.InventoryPresenter` (puente a query services + use cases → view-models y `(ok,msg,data)`, sin SQL), `navigation` (registro declarativo de 10 páginas con permiso granular `INVENTORY_*` + tooltip es-MX + `visible_entries`), páginas PyQt5 presentation-only con componentes JUANIS (`InventoryDashboardPage` KPIBar+tabla disponibilidad, `ReplenishmentPage` tabla+generar). Guardrail: sin SQL/DB en la UI, permisos de navegación válidos | `frontend/desktop/modules/inventory/**` + tests (13) | ✅ |
| INV-26 | Impresión/etiquetas (lote, peso, transferencias, conteos, reimpresión, auditoría) | renderers + print gateway | ⏳ |
| **INV-27** | **Cutover flag-gated (sin DROP destructivo aún)**: `backend/application/inventory/cutover/` — `is_cutover_enabled` (flag env `INVENTORY_CANONICAL_CUTOVER` o setting GLOBAL, **OFF** por defecto), `CanonicalInventoryCutover.wire/unwire/neutralize_legacy` (subscribe los 7 handlers canónicos al bus vivo y neutraliza los legacy sólo con el flag ON — reversible), `InventoryReconciliationService` (paridad disponible canónico vs stock legacy, drift, `is_in_sync`); migración diferida `migrations/deferred/legacy_inventory_drop.py` (**no registrada** en engine, env-guard `INVENTORY_ALLOW_LEGACY_DROP=1`); reporte `inventory_legacy_removal_report.md`. Nada cambia en runtime con flag OFF; el DROP y el repunte de lectores quedan como pasos manuales documentados | `backend/application/inventory/cutover/**` + `inventory_legacy_removal_report.md` + tests (12) | ✅ |
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
