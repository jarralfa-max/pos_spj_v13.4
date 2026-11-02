# Matriz de brechas — `activos.md` (EAM / Activos, §1–§115)

- **Fecha:** 2026-10-29 · **Commit base:** `30d3661f` · **Rama:** `sdlc/sdlc-wa-002`
- **Método:** `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (modo C). Cinco subagentes de lectura en paralelo, por grupo de secciones: (A) §1–§10, §57, §62, §109–§110; (B) §11–§21, §44–§48, §63–§65, §69–§70, §88, §108; (C) §22–§43, §59–§61, §66–§68; (D) §52–§58, §86–§87, §105–§107; (E) §71–§85, §89–§104, §111. Los informes `docs/refactor/ASSET-0…24_*.md` (pipeline de septiembre) **no** se tomaron como evidencia: se auditó el código. Los hallazgos que sostienen ítems T0 (FIN-002, FIN-003, rutas, composición vacía) se volvieron a leer directamente al consolidar.
- **Rutas** relativas a `pos_spj_v13.4/`.
- **El documento trae su propio orden de fases** (§112, ASSET-0…24). Se respeta como orden de dependencias en la columna «Depende de» del backlog, pero cada fase se ejecuta como ítems SDLC, nunca como una corrida larga.

Estados: `implementado y probado` · `parcial` · `documentado no implementado` · `defectuoso` · `duplicado` · `ausente`.

## Mediciones ejecutadas en esta sesión

| Medición | Resultado |
|---|---|
| `python -m pytest tests/unit/assets -q` | **201 passed** (todas de dominio puro o de UI con presentador falso) |
| `python -m pytest tests/architecture/test_asset*.py -q -rs` (21 archivos) | **28 passed, 1 skipped**: `test_assets_use_uuidv7.py:35` — «assets_schema.py no existe aún» |
| Pruebas de activo fijo de Finanzas (`tests/unit/finance/test_finance_domain_round2.py`, `tests/integration/finance/test_audit_fin_d9f2bca_figures.py`, `test_treasury_reconciliation_budget_assets.py`) | **72 passed** |
| Pruebas sueltas legacy `tests/test_asset_service_ui_reads.py`, `tests/test_fase3_depreciacion.py`, `tests/test_fase1_uiux_module_guards.py` (subagente A) | **20 failed, 8 errors** (`ModuleNotFoundError: core…`); no están en ningún job de CI |
| `tests/ui/*asset*` | 48 passed, pero son de **marca** (brand assets), no de Activos |
| Pruebas de integración/e2e de Activos con SQLite real | **ninguna existe** |

## Resumen

**Lectura general.** El documento se escribió contra un estado que ya no existe: `modulos/activos.py`, `core/services/asset_service.py` y `core/app_container.py` están **borrados**. Lo que hay hoy son tres capas desconectadas:

1. **EAM nuevo (`backend/domain/assets/`, `backend/application/assets/`, `frontend/desktop/modules/assets/`)**: 26 entidades con máquinas de estado, 83 permisos, ~75 constantes de eventos, 25 puertos y 6 servicios de consulta. **No tiene persistencia, ni casos de uso, ni llamadores.** El shell lo compone con `query_services={}` (`frontend/desktop/modules/assets/shell_registration.py:81-87`): de 36 rutas, 5 tienen página y siempre salen vacías, y 31 muestran «sección en construcción».
2. **Activo fijo de Finanzas (`fixed_assets`, `CapitalizeAssetUseCase`, `RunDepreciationUseCase`, `DisposeAssetUseCase`)**: es **el único inventario de activos con datos reales** y asienta balanceado por `PostingEngine`. Vive en Finanzas → «Activos fijos» y «Depreciación» (`frontend/desktop/modules/finance/finance_view.py:76-77`). No está enlazado con el EAM.
3. **Restos legacy:** seis tablas que se siguen creando y nadie lee, pruebas que importan `core/` borrado y andamiaje muerto con `float`.

**El hallazgo de mayor riesgo no está en Activos sino en la frontera Compras–Finanzas (SDLC-FIN-002).** Una compra con naturaleza `ASSET` carga la cuenta de activo contra CxP sin crear el registro en `fixed_assets`, así que ese activo nunca se deprecia. La única forma de darlo de alta después (`CapitalizeAssetUseCase`) exige tesorería o proveedor y vuelve a reconocer el pasivo o el pago.

**Funcionalidad legacy perdida sin reemplazo** (contra §4 y la regla de preservación de `CLAUDE.md`): etiquetas y QR, exportación PDF, registro de costo de mantenimiento, capitalización de mejoras, la corrida mensual automática de depreciación y el catálogo de equipos con mantenimientos. Hoy no hay forma de registrar un equipo ni un mantenimiento en la app.

| Sección | Requisitos | Implementado y probado | Brechas → ítems |
|---|---|---|---|
| §1–§5 Auditoría inicial, frontera, principio rector, preservación | 6 | 1 | FIN-002, FIN-004, ASSET-003, ASSET-004, ASSET-024, ASSET-027, ASSET-035 |
| §7–§10 Módulo global, navegación, rutas, archivos | 4 | 1 | ASSET-001 (enlazado), ASSET-005, ASSET-010, ASSET-012; UI-017 (enlazado) |
| §11–§18 Registro: agregado, UUIDv7, folio, tag, tipos, estados, criticidad, ubicaciones | 8 | 0 | ASSET-008, ASSET-009, ASSET-010 |
| §19–§21 Custodia, transferencias, préstamos | 3 | 0 | ASSET-008, ASSET-014, ASSET-015 |
| §22–§29 Mantenimiento y costos | 8 | 0 | ASSET-016…ASSET-019 |
| §30–§36 OPEX/CAPEX, capitalización, costo, depreciación, mejoras | 7 | 1 | FIN-003, FIN-004, ASSET-023, ASSET-024; CORE-006 (enlazado) |
| §37–§43 Inspecciones, checklists, medidores, garantías, seguros, documentos, fotos | 7 | 0 | ASSET-009, ASSET-017, ASSET-021, ASSET-022 |
| §44–§48 Inventario físico, diferencias, baja, venta, pérdida/robo | 5 | 0 | ASSET-008, ASSET-025, ASSET-026 |
| §49–§51 Etiquetas, formato, PDF | 3 | 0 | ASSET-027 |
| §52–§58 Integraciones (Compras, Finanzas, Tesorería, Inventario, RRHH, Configuración, BI) | 8 | 1 | FIN-002, ASSET-014, ASSET-016, ASSET-019, ASSET-020, ASSET-024, ASSET-028, ASSET-030, ASSET-031 |
| §59–§62 MTBF/MTTR, salud, reemplazo, configuración | 4 | 0 | ASSET-030, ASSET-031 |
| §63–§70 QueryServices y casos de uso | 8 | 0 | ASSET-011…ASSET-016, ASSET-021, ASSET-023, ASSET-025, ASSET-026 |
| §71–§85 Permisos, roles, scopes, SoD, autorización en caliente | 7 | 1 | ASSET-005, ASSET-006, ASSET-007, ASSET-008, ASSET-029 |
| §86–§88 Auditoría, eventos, idempotencia | 3 | 0 | ASSET-010, ASSET-011 |
| §89–§104 UI/UX | 16 | 2 | ASSET-012, ASSET-013, ASSET-018, ASSET-030, ASSET-033; UI-007, UI-021 (enlazados) |
| §105–§108 Offline, conflictos, notificaciones, excepciones | 4 | 0 | ASSET-009, ASSET-017, ASSET-022, ASSET-032 |
| §109–§111 Eliminación de legacy, guardrails, tests funcionales | 3 | 0 | ASSET-002, ASSET-003, ASSET-004 |

Los IDs abreviados se refieren a `SDLC-<…>`. Los marcados «(enlazado)» ya estaban en el backlog y cubren esa parte. §6 (skills), §112 (fases), §113 (definición de terminado), §114 (reporte final) y §115 (regla final) no son requisitos sueltos: §113 se responde con esta matriz y §115 se traduce en los ítems de fuente única (FIN-002, ASSET-024, ASSET-026, ASSET-034).

## §1–§5 Auditoría inicial, frontera Activos/Finanzas, preservación

| § | Requisito | Estado | Evidencia | Prueba que lo cubre | Ítem |
|---|---|---|---|---|---|
| §1/§5 | No conservar `modulos/activos.py`, `AssetService` monolítico, `container` | implementado y probado | Los tres archivos no existen (borrados en `a35b8bab`). Quedan comentarios que citan `core/app_container.py` como raíz viva: `backend/application/sales/session_authorization.py:6` y análogos en loyalty y orders_delivery | `tests/architecture/test_assets_have_no_legacy_imports.py` | ASSET-003 (comentarios) |
| §2 | Activos dueño del ciclo físico; Finanzas del valor contable | parcial | La frontera existe en las guardias (`tests/architecture/test_assets_do_not_post_journal_entries.py`, `test_assets_do_not_own_financial_depreciation.py`), pero pasan en vacío porque Activos no tiene código de escritura. En la práctica **Finanzas es hoy dueño de todo el ciclo**: alta, suspensión, reactivación y baja en `frontend/desktop/modules/finance/pages/fixed_assets_page.py:30-34,47-93` | guardias (vacías) | ASSET-024, ASSET-026 |
| §2/§52/§53 | Una compra de activo produce **un** reconocimiento | **defectuoso** | Compra `ASSET` → `asset_account_id` (`backend/application/event_handlers/finance/procurement_posting_policy.py:21-25`); el puente crea CxP y asienta sin `FixedAsset` (`procurement_payable_bridge.py:69-107`). `CapitalizeAssetUseCase` exige tesorería **o** proveedor (`backend/application/use_cases/finance/capitalize_asset_use_case.py:56-59`) y crea otra CxP (`:87-100`) | ninguna | **FIN-002 (P0)** |
| §4 | Preservar funciones válidas (etiquetas, PDF, costo, pago, capitalización, depreciación, bajas, reportes) | defectuoso | Perdidas sin reemplazo: etiquetas y PDF (solo `PrintJobGatewayPort`, `backend/domain/assets/integration_ports.py:69-75`), costo de mantenimiento, capitalización de mejoras, corrida mensual de depreciación (no hay scheduler; solo `frontend/desktop/modules/finance/pages/depreciation_page.py:35`), listado y alta de equipos | ninguna | ASSET-016, ASSET-019, ASSET-023, ASSET-027, FIN-004 |
| §4 | Inventarios `docs/refactor/assets_*.md` (7) | parcial | Existen `assets_legacy_inventory.md` y `assets_finance_boundary_map.md`; faltan `feature_inventory`, `business_logic_map`, `ui_inventory`, `permission_inventory` y `legacy_removal_report`. `migrations/MIGRATION_LOG.md:2998` dice que `activos_depreciacion` tiene «escritor vivo»: ya no es cierto | — | ASSET-035 |
| §5 | Sin float monetario, sin `IDs int`, sin `uuid4` | parcial | El EAM cumple. Fuera de él: `backend/application/commands/asset_commands.py:17,45` (`float`) y columnas REAL en las tablas legacy (`migrations/m000_base_schema.py:1445-1449,1464,1480-1482,1495,3073-3075`) | `tests/architecture/test_assets_use_decimal.py` (no escanea esos archivos) | ASSET-003, ASSET-004 |

## §7–§10 Módulo global, navegación, rutas, archivos

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §7 | Activos como módulo global, no dentro de Finanzas | duplicado | Entrada global `nav.assets` (`frontend/desktop/shell/sidebar/migrated_modules_navigation.py:216-220`). Finanzas mantiene su propio grupo «Activos» con datos reales (`frontend/desktop/modules/finance/finance_view.py:76-77`) | `tests/unit/shell/sidebar/test_migrated_modules_navigation.py:113` | ASSET-024; UI-017 y ASSET-001 (enlazados) |
| §8 | Navegación interna con ModuleSidebar | parcial | Usa `SideNav` (`frontend/desktop/modules/assets/assets_workspace.py:28,53`); los grupos de §8 existen como rutas | `tests/unit/assets/test_assets_ui_foundations.py` | ASSET-012 |
| §9 | 36 rutas canónicas | parcial | 36 rutas en `assets_routes.py:52-178`; 5 con página (`assets_workspace.py:120-132`), 31 en «sección en construcción» (`:134-138`). El filtro de rutas **ignora `required_permission`** (`assets_routes.py:180-186`, *verificado directamente*) | `tests/architecture/test_asset_routes_are_registered.py` (solo busca 3 cadenas) | ASSET-005, ASSET-012…; ASSET-001 |
| §10 | Arquitectura de archivos dominio / aplicación / infraestructura / frontend | parcial | Dominio y frontend sí. En aplicación faltan `commands/`, `use_cases/`, `event_handlers/`. No existe `backend/infrastructure/assets/`, ni `backend/infrastructure/db/repositories/assets/`, ni `backend/infrastructure/db/schema/assets_schema.py` | `tests/unit/assets/*` | ASSET-010, ASSET-011 |

## §11–§18 Registro de activos

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §11 | Agregado `Asset` con los campos de §11 | parcial | `backend/domain/assets/entities/asset.py:44-75` (falta `asset_tag`; `version` nunca se incrementa, `:73`; `relocate()` cambia de sucursal sin transferencia, `:140-146`). Sin persistencia | `tests/unit/assets/test_asset_entity.py` | ASSET-008, ASSET-010 |
| §12 | UUIDv7 en todas las identidades | parcial | Dominio con `new_uuid()` de `backend/shared/ids.py:53`. Sin tablas EAM; las tablas legacy tienen PK TEXT y se siguen creando | `test_assets_use_uuidv7.py` (skip del esquema, `:35`) | ASSET-002, ASSET-010 |
| §13 | Folio operativo configurable | ausente | `asset.py:82-83` solo valida no vacío; sin generador, secuencia ni UNIQUE | ninguna | ASSET-010, ASSET-031 |
| §14 | AssetTag con token QR seguro, Code128 | parcial | `backend/domain/assets/entities/asset_tag.py:29-91`; el token es `new_uuid()` (UUIDv7, deja ver la fecha), `:56`; Code128 solo enum (`enums.py:271`) | `test_asset_tag.py` | ASSET-009, ASSET-027 |
| §15 | Tipo y categoría configurables con seed | parcial | `asset_category.py:22-62`; no hay `AssetType` ni seed; ruta `assets.categories` sin página | `test_asset_category_and_location.py` | ASSET-010, ASSET-031 |
| §16 | Estados y condición como enums | parcial | `enums.py:8-31`; `change_condition` sin validación, `AssetConditionInvalidError` nunca se lanza | `test_asset_entity.py` | ASSET-009 |
| §17 | Criticidad que impacte frecuencia, SLA, alertas, prioridad | parcial | `enums.py:34-38`; no impacta nada (`maintenance_plan.py:38`, `maintenance_work_order.py:52` usan MEDIUM fijo) | ninguna | ASSET-016, ASSET-031 |
| §18 | Ubicación jerárquica | defectuoso | `asset_location.py:44` exige padre a todo lo que no sea BRANCH, incluido COMPANY (raíz): imposible de crear. Sin validación de ciclos | `test_asset_category_and_location.py` | ASSET-009, ASSET-010 |

## §19–§21 Custodia, transferencias, préstamos

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §19 | Asignación con historial completo | parcial | `asset_assignment.py:23-66` (solo dominio). Nada impide dos asignaciones activas | `test_asset_assignment_and_loan.py` | ASSET-014 |
| §20 | Transferencia con estados y actores; no por UPDATE | parcial | `asset_transfer.py`; `approve` sin segregación de funciones (`:76-82`, *verificado directamente*); `cancel` permitido en IN_TRANSIT (`:116`); `Asset.relocate()` la salta | `test_asset_transfer.py` | ASSET-008, ASSET-015 |
| §21 | Préstamos | parcial | `asset_loan.py:21-62` (solo dominio, sin enum de estado) | `test_asset_assignment_and_loan.py` | ASSET-014 |

## §22–§29 Mantenimiento y costos

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §22 | Plan / WorkOrder / Execution / Task / Resource | parcial | Solo `maintenance_plan.py:29` y `maintenance_work_order.py:45`; Execution, Task y Resource no existen | `test_maintenance_plan_and_work_order.py` | ASSET-016 |
| §23 | Plan preventivo con frecuencias y `next_due_at` | parcial | `enums.py:106-114`, `maintenance_plan.py:35-66`; nada recalcula `next_due_at` | idem | ASSET-016 |
| §23/§39 | Generación automática de OT por vencimiento o medidor | ausente | Sin job ni `GenerateMaintenanceWorkOrderUseCase`; `meter_trigger` es texto libre (`maintenance_plan.py:36`); `scripts/weekly_maintenance.py` solo hace VACUUM e importa `core.database` (inexistente) | ninguna | ASSET-017, ASSET-003 |
| §24/§25 | OT con folio, 12 estados, downtime, causa raíz | parcial | `maintenance_work_order.py:46-183`; folio lo pasa el llamador (`:77-78`), sin UNIQUE; `approve` sin SoD (`:101-107`) | idem | ASSET-008, ASSET-016 |
| §26/§27 | Tipos; proveedor interno/externo/garantía | parcial | `enums.py:95-126`; `assign()` nunca produce WARRANTY_PROVIDER (`maintenance_work_order.py:122-124`) | idem | ASSET-009, ASSET-016 |
| §28 | Consumir el lookup de proveedores de Compras | ausente | Solo `SupplierLookupPort` (`integration_ports.py:31`) sin adaptador; Compras tiene `supplier_directory_query_service.py:22` | `test_integration_ports.py` (solo forma) | ASSET-016 |
| §29 | Costos en Decimal con desglose; `MAINTENANCE_COST_CONFIRMED` hacia Finanzas/Compras | parcial | Solo `estimated_cost`/`actual_cost` (`maintenance_work_order.py:62-63`); el evento es una constante sin productor (`events.py:58`). El costo real no llega a ningún lado | guardias negativas | ASSET-019 |

## §30–§36 OPEX/CAPEX, capitalización, depreciación, mejoras

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §30/§31 | Propuesta de capitalización → Finanzas aprueba y asienta | parcial | `asset_capitalization_proposal.py:43-124` (solo dominio); `approve` sin SoD contra `submitted_by` (`:90-94`); `cancel` acepta APPROVED (`:117-124`, *verificado directamente*). En Finanzas no hay `ApproveCapitalization`/`PostCapitalization`; `CapitalizeAssetUseCase` solo da de alta activos **nuevos** | `test_asset_capitalization.py` | ASSET-008, ASSET-023 |
| §32 | Separar costo de adquisición, costo operativo, proyección de valor | ausente | `Asset.financial_asset_id` (`asset.py:63`) no persiste en ningún lado | ninguna | ASSET-024 |
| §33/§35 | Depreciación contable en Finanzas | implementado y probado (solo línea recta) | `backend/domain/finance/policies/depreciation_policy.py:10-33`; `run_depreciation_use_case.py:29-81` asienta por PostingEngine; solo `STRAIGHT_LINE` (`backend/domain/finance/enums.py:275-276`). La corrida es **manual** (la legacy era mensual automática) | `test_treasury_reconciliation_budget_assets.py:220-239`; `test_finance_domain_round2.py:455,464` | FIN-004; CORE-006 (enlazado: suma con la moneda del primer activo) |
| §34 | `AssetFinancialProjectionQueryService` | ausente | Solo citado por la guardia `test_assets_do_not_own_financial_depreciation.py:6,44`; ruta `assets.depreciation_projection` sin página | guardia | ASSET-024 |
| §36 | AssetImprovement | parcial | `asset_improvement.py:24-55` (solo dominio) | `test_asset_capitalization.py` | ASSET-023 |
| §46/§47 (Finanzas) | Baja/venta con valor en libros correcto | **defectuoso** | `dispose_asset_use_case.py:57-69` toma `net_book_value()` sin exigir depreciación hasta el periodo de baja (*verificado directamente*); `DisposeAssetUseCase` y `ChangeAssetStatusUseCase` (`:114-138`) **sin pruebas** | ninguna | FIN-003 |

## §37–§43 Inspecciones, medidores, documentación

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §37 | Inspecciones con resultados | parcial | `asset_inspection.py:30-79`; respuestas no se validan contra la plantilla (`:61-72`); OUT_OF_SERVICE no cambia el activo ni crea OT | `test_asset_inspection.py` | ASSET-009, ASSET-021 |
| §38 | Plantillas de checklist configurables | parcial | `inspection_checklist_template.py:15-61` (solo dominio) | idem | ASSET-021 |
| §39 | Medidores y lecturas | parcial | `asset_meter.py:42-49`, `asset_meter_reading.py:29-41` (solo dominio) | `test_asset_meter.py` | ASSET-017 |
| §40 | Garantías con alerta previa | parcial | `asset_warranty.py:47-63` (30 días fijos); `AssetWarrantyQueryService` sin repositorio (`asset_read_services.py:119-128`); sin productor de `ASSET_WARRANTY_EXPIRING` (`events.py:73`) | `test_asset_documentation.py` | ASSET-022 |
| §41 | Seguros | defectuoso | `asset_insurance_policy.py:61-68` nunca produce EXPIRING aunque el enum lo define | idem | ASSET-009, ASSET-022 |
| §42 | Documentos con `DocumentStorageGateway` | parcial | `asset_document.py:25-62`; `DocumentStorageGatewayPort` sin adaptador (`integration_ports.py:60`) | idem | ASSET-022 |
| §43 | Fotos con MIME, tamaño, hash, metadata | parcial | `asset_document.py:17,46-54`: MIME y hash solo «no vacíos», 25 MB fijo; sin metadata | idem | ASSET-009, ASSET-022 |

## §44–§48 Inventario físico y bajas

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §44 | Inventario físico con escaneo | parcial | `asset_physical_inventory.py`, `asset_physical_inventory_line.py:24-35` (línea sin `operation_id`: escaneo repetido no idempotente); sin resolución de QR | `test_asset_physical_inventory.py` | ASSET-009, ASSET-025 |
| §45 | Diferencias con workflow | parcial | `asset_physical_discrepancy.py` (SoD en `:79-81`) | idem | ASSET-025 |
| §46 | Baja por solicitud y aprobación | duplicado | EAM: `asset_disposal_request.py`, `asset_disposal.py` (solo dominio). Finanzas da de baja sin ese flujo: `dispose_asset_use_case.py:43,114` desde `finance_routes.py:270-271` | `test_asset_disposal.py` | ASSET-026 |
| §47 | Venta de activo | parcial | Solo en Finanzas (`dispose_asset_use_case.py:47-56`); `AssetDisposal` sin comprador ni documento | ninguna | ASSET-026 |
| §48 | Pérdida/robo con evidencia y alerta | parcial | `asset_disposal_request.py:49,57,64`: evidencia opcional; sin evento ni alerta (no hay LOST/STOLEN en `events.py`) | `test_asset_disposal.py` | ASSET-008 |

## §49–§51 Etiquetas y PDF

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §49/§50 | Etiquetas configurables por Document Output → PrintJob | ausente | `PrintJobGatewayPort` (`integration_ports.py:69-75`) sin implementación; ruta `assets.tags` en construcción. La capacidad legacy se perdió | ninguna | ASSET-027 |
| §51 | Reporte PDF por Document Output | ausente | idem | ninguna | ASSET-027 |

## §52–§58 Integraciones

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §52 | Compras → solicitud de registro de activo con política | ausente | `ASSET_REGISTRATION_REQUESTED` no existe en código; traductores downstream sin activos (`backend/application/procurement/integrations/downstream_events.py:12-19`) | `tests/unit/procurement/test_purchase_routing_policy.py:30` (solo ruteo) | ASSET-028, FIN-002 |
| §53 | Eventos de Activos consumidos por Finanzas | documentado no implementado | Constantes en `backend/domain/assets/events.py:21-101`; ningún productor ni suscriptor (`backend/bootstrap/wiring/event_wiring.py`, `backend/application/finance/wiring.py`) | `test_integration_ports.py:27-41` (catálogo) | ASSET-011, ASSET-019, ASSET-023, ASSET-026 |
| §53 | Vía de Finanzas para activo fijo y depreciación con asiento balanceado | implementado y probado | `capitalize_asset_use_case.py:42-125`, `run_depreciation_use_case.py`, `dispose_asset_use_case.py`, todo por PostingEngine | `test_treasury_reconciliation_budget_assets.py:220`; `test_audit_fin_d9f2bca_integrity.py:269` | — (salvo FIN-002/003) |
| §54 | Tesorería solo por CxP; nunca pago desde Activos | parcial | Se cumple la prohibición porque no hay código; la cadena OT → gasto/CxP no existe | guardias (vacías) | ASSET-019 |
| §55 | Refacciones por solicitud a Inventario | ausente | No hay `PartsRequest` en ningún sitio | `test_assets_parts_do_not_write_inventory.py` (vacía) | ASSET-020 |
| §56 | Consumir el lookup de empleados de RRHH | ausente | `EmployeeLookupPort` sin adaptador (`integration_ports.py:47-49`); RRHH tiene `backend/application/queries/hr/hr_query_services.py:53,68,90` | ninguna | ASSET-014 |
| §57 | Referencia a `device_registration_id` | ausente | `Asset` no tiene el campo; `DeviceRegistrationLookupPort` sin implementación (`integration_ports.py:52-57`) | ninguna | ASSET-031 |
| §58 | Métricas de activos para BI | ausente | Nada de activos en `backend/application/analytics*` | ninguna | ASSET-030 |

## §59–§62 Indicadores y configuración

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §59 | MTBF / MTTR | ausente | Sin resultados en código | ninguna | ASSET-030 |
| §60 | Health score explicable | ausente | idem | ninguna | ASSET-030 |
| §61 | Candidatos a reemplazo | ausente | idem | ninguna | ASSET-030 |
| §62 | Configuración del módulo versionada y auditada | ausente | Ruta `assets.settings` en construcción (`assets_routes.py:175-177`); sin tabla de settings | ninguna | ASSET-031 |

## §63–§70 QueryServices y casos de uso

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §63 | 17 QueryServices | parcial | 6 en `backend/application/assets/queries/asset_read_services.py:46-140`, sobre puertos sin implementación; faltan 11. La UI recibe `{}` (`shell_registration.py:81-87`, *verificado directamente*) | `test_asset_read_services.py` (fakes) | ASSET-012 y siguientes |
| §64 | Casos de uso de activos (6) | ausente | No existe `backend/application/assets/use_cases/` | ninguna | ASSET-011 |
| §65 | Asignación, transferencia, préstamo (6) | ausente | idem | ninguna | ASSET-014, ASSET-015 |
| §66 | Mantenimiento (11) | ausente | idem; el andamiaje `schedule_maintenance_use_case.py:9` / `complete_maintenance_use_case.py:9` devuelve `not_implemented` | ninguna | ASSET-016, ASSET-017 |
| §67 | Inspección (4) | ausente | idem | ninguna | ASSET-021 |
| §68 | Capitalización (3 en Activos, 2 en Finanzas) | ausente | idem | ninguna | ASSET-023 |
| §69 | Inventario físico (5) | ausente | idem | ninguna | ASSET-025 |
| §70 | Baja (6) | ausente (en EAM) | idem | ninguna | ASSET-026 |

## §71–§85 Permisos, roles, scopes, SoD

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §71–§81 | Permisos granulares (convención del repo `ACTIVOS.accion`) | parcial | 83 códigos en `backend/application/assets/permissions.py:24-128`, en el catálogo vía `backend/application/security/permission_catalog.py:61`. **Ninguno sembrado**: fuera de `_SEEDED_MODULES` (`:97-102`) y de `migrations/m000_base_schema.py:3188-3193`; `rol_permisos` real con 0 filas ACTIVOS. Solo entra `system_owner` por el comodín `*` (`backend/security/permissions/principals.py:29-30`). La política `AssetAuthorizationPolicy.require` (`authorization.py:59-70`) no la usa nadie | `test_asset_permissions_are_granular.py` (forma) | ASSET-005, ASSET-006, ASSET-011 |
| §77 | Activos sin permisos de asiento ni pago | implementado y probado | `permissions.py:14-16,87-88` | `test_asset_permissions_are_granular.py:26-34` | — |
| §82 | Roles sugeridos ASSET_* | ausente | No aparecen en código ni migraciones | ninguna | ASSET-006 |
| §83 | Scopes + `AssetDataScopeResolver` | documentado no implementado | Solo Protocol (`backend/application/assets/scopes.py:21-49`); los servicios no filtran; sin sucursal, el tablero hace `list_all()` (`asset_read_services.py:89`) | `test_asset_scopes_are_enforced.py` (solo el enum) | ASSET-007 |
| §84 | Segregación de funciones | parcial | Sí en baja, recepción de transferencia y diferencia de inventario; no en aprobación de transferencia, OT y capitalización | `test_asset_disposal.py:52-56`, `test_asset_transfer.py:54` | ASSET-008 |
| §85 | Autorización en caliente sin PIN local | ausente | `authorize_exception` (`authorization.py:72-83`) sin uso ni verificador común (`backend/application/security/authorizer_permission_checker.py`) | ninguna | ASSET-029 |

## §86–§88 Auditoría, eventos, idempotencia

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §86 | Auditoría de toda mutación | ausente | Ninguna mutación escribe auditoría; el docstring de `authorization.py:7` dice «always audited» y no es cierto; no existe `AssetAuditQueryService` | ninguna | ASSET-011 |
| §87 | Eventos post-commit con `event_id`, `operation_id`, `entity_id`, `occurred_at` | documentado no implementado / duplicado | ~75 constantes en `events.py:19-108`, ninguna publicada; `build_event_payload` usa `timestamp` y no lleva `entity_id` (`events.py:134-149`); catálogo paralelo `backend/shared/events/event_names.py:49-51` (`ASSET_CREATED`, `MAINTENANCE_*`) sin productor | catálogo | ASSET-011 |
| §88 | UNIQUE(operation_id, asset_number, serial, tag_number) | ausente | Sin tablas EAM; `ProcessedEventRepositoryPort`/`OutboxRepositoryPort` sin implementación (`repository_ports.py:235-247`) | ninguna | ASSET-010, ASSET-011 |

## §89–§104 UI/UX

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §89/§90 | Solo Design System; sin QSS, hex, emoji, QTableWidget… | implementado y probado | Sin hallazgos en `frontend/desktop/modules/assets/`; no usa StatusBadge, FilterBar, MoneyInput ni ChartView | `test_assets_have_no_*`, `test_assets_use_design_system.py` (este último tautológico, `:23-25`) | ASSET-002 |
| §91 | Dashboard ≤6 KPIs calculados fuera de la UI | parcial | 5 KPIs de conteo (`asset_read_services.py:88-96`, `pages/overview_page.py:91-105`); faltan valor, vencidos, OT abiertas, costo | `test_assets_ui_pages.py:46,57` | ASSET-030 |
| §92 | Gráficas por ChartDTO/ECharts | ausente | `components/chart_view.py` existe sin usar | ninguna | ASSET-030 |
| §93 | Directorio con filtros y columnas | parcial | Solo búsqueda y estado; 5 columnas (`assets_directory_page.py:68-81`) | `test_assets_ui_pages.py:71-94` | ASSET-012 |
| §94 | Detalle con pestañas con route_id | parcial | Un panel (`asset_detail_page.py:37-52`); enums crudos (`:86-88`); `except Exception` que traga el error (`:72-75`) | `test_assets_ui_pages.py:111-132` | ASSET-012, ASSET-033 |
| §95 | Tablero de OT Kanban/Tabla/Calendario operable | parcial | Kanban estático de solo lectura (`work_orders_board_page.py:4-13,103-107`) | `test_assets_maintenance_ui.py:60-85` | ASSET-018 |
| §96 | Agenda día/semana/mes | parcial | Tabla ordenada (`maintenance_agenda_page.py:63-71`) | `test_assets_maintenance_ui.py:99-115` | ASSET-018 |
| §97/§98/§99 | Formularios de activo y de OT con MoneyInput | ausente | `assets.create` es un marcador (`assets_workspace.py:134-136`) | ninguna | ASSET-013, ASSET-018 |
| §100 | Responsive 1366×768…1920×1080 | implementado y probado | | `test_assets_responsive_touch.py:35-81` | — |
| §101/§102 | Densidades y teclado virtual | ausente | El módulo no usa densidades ni `KeyboardAwareInput` | ninguna | UI-007, UI-021 (enlazados) |
| §103 | IconProvider | parcial | `components/icons.py:42-43,74,96,107`; no hay `TOOLS`; DISPOSAL e INSPECTION son alias | ninguna | ASSET-033 |
| §104 | Accesibilidad | parcial | AccessibleName en contenedores; etiquetas del detalle sin nombre ni buddy (`asset_detail_page.py:48-51`); tarjetas de OT sin foco (`work_orders_board_page.py:52-66`) | `test_assets_responsive_touch.py:83-90` | ASSET-033 |

## §105–§108 Offline, notificaciones, excepciones

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §105 | Mutaciones offline con outbox y `sync_status` | documentado no implementado | `AssetSyncStatus` (`enums.py:278-283`); Activos no está en `backend/infrastructure/sync/replication_sources.py:132-148` | ninguna | ASSET-032 |
| §106 | Conflictos offline sin sobrescritura silenciosa | documentado no implementado | `asset_sync_conflict.py:1-21` se declara «solo vocabulario» | `test_asset_sync_conflict.py` (dominio) | ASSET-032 |
| §107 | Notificaciones de vencimientos, faltantes, bajas | ausente | Sin productor; `backend/application/notifications/user_inbox_service.py` no conoce activos | ninguna | ASSET-017, ASSET-022 |
| §108 | Excepciones de dominio; prohibido `except Exception: pass` | parcial | `backend/domain/assets/exceptions.py`; `AssetAlreadyExistsError`, `DuplicateOperationError`, `AssetTagDuplicateError`, `AssetConditionInvalidError`, `InvalidMoneyError` nunca se lanzan (`:14,22,43,48,165`); el docstring de `:166-168` afirma una UNIQUE que no existe | — | ASSET-009, ASSET-033 |

## §109–§111 Legacy, guardrails, tests funcionales

| § | Requisito | Estado | Evidencia | Prueba | Ítem |
|---|---|---|---|---|---|
| §109 | Eliminar legacy de Activos | parcial | Archivos borrados; quedan: pruebas que importan `core/` (`tests/test_asset_service_ui_reads.py:35`, `tests/test_fase3_depreciacion.py:60`, `tests/test_fase1_uiux_module_guards.py:11`), `scripts/weekly_maintenance.py:1`, andamiaje muerto (`backend/application/commands/asset_commands.py`, `use_cases/create_asset_use_case.py`, `schedule_maintenance_use_case.py`, `complete_maintenance_use_case.py`, `queries/asset_query_service.py`), y seis tablas que se siguen creando (`m000_base_schema.py:88,1441,1459,1472,1490,3070`; `standalone/060_depreciacion_acumulada.py:9`) | — | ASSET-003, ASSET-004 |
| §110 | 21 guardrails | defectuoso | Los 21 existen, pero varios pasan sin comprobar nada: raíz de infraestructura y esquema inexistentes tratados en silencio (`tests/architecture/assets_guardrails.py:29,33,62-64`); `test_assets_use_decimal.py:44-45` hace `return`; rutas, scopes y design system sin verificación real; `ORPHANED_ASSET_SCAFFOLDING` (`:55-59`) con prefijo erróneo y sin uso; `LEGACY_ASSET_FILES` vacío (`:50-51`) | se cubren a sí mismas | ASSET-002 |
| §111 | Tests funcionales (crear, asignar, transferir, OT, inspección, inventario, baja, etiquetas) | ausente | Solo dominio puro y UI con presentador falso; ninguna prueba de flujo con persistencia | — | cada ítem de construcción trae los suyos |

## Defectos fuera del alcance del documento encontrados en el barrido

- `frontend/desktop/modules/finance/pages/fixed_assets_page.py:20`: `ColumnSpec("Código", "date")` (tipo equivocado) → incluido en ASSET-033.
- `backend/application/meat_processing/use_cases/resource_use_cases.py:171-196`: un ciclo de mantenimiento de equipos propio en Procesamiento Cárnico, con auditoría `operation_id=None` (`:193-194`) → ASSET-034 (§115: una sola arquitectura de mantenimiento).
- `../.github/workflows/ci-segmented.yml:125,146,167` llama a `./scripts/ci/run_domain_tests.sh`, que no existe → ya cubierto por SDLC-UI-001.
