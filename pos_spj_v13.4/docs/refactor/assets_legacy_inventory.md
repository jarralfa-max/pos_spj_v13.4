# ASSET-0 — Inventario legacy: Activos / EAM

> Auditoría inicial del bounded context de Activos, previa a la transformación enterprise EAM.
> Fecha: 2026-09-02

## 1. UI legacy — `modulos/activos.py` (696 líneas)

Clase `ModuloActivos(ModuloBase)`, 3 tabs: Inventario de Equipos, Agenda/Órdenes de Servicio, Depreciación Acumulada. Incluye `DialogoActivo` y un diálogo de pago/cierre de mantenimiento.

| Hallazgo | Detalle |
|---|---|
| Container access | `container.db` (via `super().__init__`) + `self.container.asset_service.completar_y_pagar_mantenimiento(...)` llamado directo desde UI |
| SQL directo en archivo | No se detectó SQL embebido directo (remediación previa parcial: `DialogoActivo` ya es "captura-only") |
| QTabWidget | 1 (`self.tabs`) — navegación principal por tabs |
| QTableWidget | 3 (`tabla_activos`, `tabla_mant`, `tabla_dep`) |
| PDF | `from fpdf import FPDF`, 2 métodos de exportación (`exportar_pdf_activos`, agenda) — FPDF crudo, sin pasar por Document Output |
| Dinero | `QDoubleSpinBox` para `spin_valor`, `spin_depreciacion` — debe ser `MoneyInput` + Decimal |
| Emojis | Uso intenso: 🚀 🛠️ 🚜 📋 🔧 📊 ➕ 🔄 📄 🏷️ ✏️ ❌ ✅ 📅 |

**Clasificación: REWRITE.**

## 2. Servicio legacy — `core/services/asset_service.py` (469 líneas)

`AssetService(db_conn, treasury_service, finance_service=None)` — god-service que mezcla:

- CRUD: `registrar_activo`, `crear_activo`, `actualizar_activo`, `dar_de_baja`, `eliminar_mantenimiento`
- Mantenimiento: `agendar_mantenimiento`, `editar_mantenimiento`, `programar_mantenimiento`, `completar_y_pagar_mantenimiento`
- Depreciación: `accrual_depreciacion_mensual`, `calcular_depreciacion_mensual`, `listar_depreciacion_acumulada`
- Capitalización: `capitalizar_mantenimiento`
- Lecturas para PDF: `listar_activos_para_pdf`, `listar_mantenimientos_para_pdf`

Transacciones manuales: `self.db.commit()` / `self.db.rollback()`, incluso SAVEPOINT manual (`SAVEPOINT sp_16f78f` / `ROLLBACK TO SAVEPOINT`).

**Acoplamiento financiero directo (viola §2 del prompt maestro):**
- `completar_y_pagar_mantenimiento()` llama `self.treasury_service.registrar_gasto_opex(...)`
- `accrual_depreciacion_mensual()` llama `self.finance_service.registrar_asiento(...)`

**Clasificación: REWRITE** — debe dividirse en domain (Asset, MaintenanceRecord/WorkOrder), application use cases (RegisterAsset, ScheduleMaintenance, CompleteMaintenanceWorkOrder, AccrueDepreciation vía Finance, CapitalizeAsset vía Finance, DisposeAsset), e infrastructure repositories.

## 3. Código domain/application/infrastructure existente

**No existe** `domain/assets/`, `application/assets/`, `backend/domain/assets/`, `backend/application/assets/`.

Existe una porción DDD limpia pero **finance-only** (CAPEX/depreciación contable), a preservar:

| Archivo | Rol | Acción |
|---|---|---|
| `backend/domain/finance/entities/fixed_asset.py` (111 líneas) | `@dataclass FixedAsset`, Money VOs, `DepreciationMethod`/`FixedAssetStatus`, `operation_id` | PRESERVE |
| `backend/domain/finance/repository_ports.py` (línea 140) | `FixedAssetRepositoryPort(Protocol)` | PRESERVE |
| `backend/infrastructure/db/repositories/finance/fixed_asset_repository.py` (91 líneas) | `FixedAssetRepository(FinanceRepositoryBase)` | PRESERVE |
| `backend/application/use_cases/finance/capital_and_asset_use_cases.py` (210 líneas) | `RegisterCapitalContributionUseCase`, `CapitalizeAssetUseCase`, `DisposeAssetUseCase` | PRESERVE (alcance financiero únicamente) |
| `backend/application/queries/finance/finance_read_services.py` | `FixedAssetQueryService` (línea 217) | PRESERVE |

Scaffolding delgado/abandonado, probablemente sin wiring:

| Archivo | Detalle | Acción propuesta |
|---|---|---|
| `backend/application/commands/asset_commands.py` (51 líneas) | `CreateAssetCommand` | REVISAR referencias, probable DELETE_DUPLICATE o absorción |
| `backend/application/queries/asset_query_service.py` (18 líneas) | `AssetQueryService(BaseQueryService)` | REVISAR referencias, probable DELETE_DUPLICATE |
| `backend/application/use_cases/create_asset_use_case.py` (10 líneas) | `CreateAssetUseCase` | REVISAR referencias, probable DELETE_DUPLICATE |

No existen clases `MaintenancePlan`, `MaintenanceWorkOrder`, `AssetTag` en ningún punto del repo.

## 4. Schema de base de datos — 3 esquemas paralelos

Todos usan PK `TEXT` (UUID), conforme a REGLA CERO ya vigente en el repo.

| Tabla | Origen | Estado | Acción |
|---|---|---|---|
| `activos` | `m000_base_schema.py` (`_create_activos`) | Legacy, usada activamente por `AssetService` | MIGRATE → canonical |
| `mantenimientos` | `m000_base_schema.py` | Legacy, usada activamente | MIGRATE → canonical |
| `activos_depreciacion` | `m000_base_schema.py` (~línea 3104) | Legacy, usada activamente | MIGRATE → canonical |
| `assets` / `asset_maintenance` | `m000_base_schema.py` (líneas 1506/1524) | Segundo esquema TEXT-PK con columnas en inglés, **no referenciado por AssetService** | DELETE candidate (confirmar 0 referencias) — **corregido en ASSET-23**: `assets` SÍ tiene consumidor real (`core/services/enterprise/finance_service.py`, reporte de balance), solo `asset_maintenance` se confirmó huérfano |
| `depreciacion_acumulada` | `migrations/standalone/060_depreciacion_acumulada.py` | Otro ledger de depreciación, `UNIQUE(activo_id, periodo)` | REVISAR — posible duplicado de `asset_depreciation_entries` |
| `fixed_assets`, `asset_depreciation_entries`, `maintenance_records` | `migrations/standalone/083_financial_traceability_tables.py` | **Esquema canónico financiero**: `operation_id`, `financial_document_id`, `treasury_movement_id`, `journal_entry_id`, `source_module/source_id/source_folio`, `capitalizable`, `metadata_json`. Documentado in-file como "Coexiste con tabla 'activos' (legacy)" | PRESERVE / EXTEND — base del nuevo modelo EAM |

**Conclusión:** el refactor EAM debe reconciliar 3 tablas de activos + 3 ledgers de mantenimiento/depreciación, migrar datos de `activos`/`mantenimientos`/`activos_depreciacion` hacia el esquema canónico (`fixed_assets`/`maintenance_records`/`asset_depreciation_entries`) o hacia un nuevo esquema EAM que lo extienda, y eliminar el par huérfano `assets`/`asset_maintenance`.

## 5. Tests existentes

| Archivo | Cobertura |
|---|---|
| `tests/test_asset_service_ui_reads.py` (148 líneas) | Caracterización pre-extracción de SQL: `listar_activos_para_tabla`, `dar_de_baja`, `listar_depreciacion_acumulada`, `listar_mantenimientos`, `eliminar_mantenimiento`, listados para PDF, `calcular_depreciacion_mensual`. **Conservar como red de regresión durante el refactor.** |
| `tests/test_fase3_depreciacion.py` (241 líneas) | Unit tests de `accrual_depreciacion_mensual` y `capitalizar_mantenimiento`, con schema `activos` in-memory propio |
| `tests/integration/finance/test_treasury_reconciliation_budget_assets.py` | Reconciliación financiera tocando activos/presupuesto (lado `fixed_assets` canónico) |

No existen tests de arquitectura (`tests/architecture/test_assets_*.py`) — a diferencia de Ventas, Productos, CRM, etc. No hay boundary DDD establecido todavía.

## 6. Ruteo UI

No existe `assets_routes.py` ni registro de rutas para Activos (a diferencia de Caja, Configuración, CRM, Finanzas, RRHH, Mermas, Cárnico, Pedidos/Delivery, Precios, Productos, Compras, Fidelidad, Transferencias — todos ya tienen `*_routes.py`).

Wiring legacy directo:
```text
interfaz/main_window.py:111   from modulos.activos import ModuloActivos
interfaz/main_window.py:670   self._conectar("ACTIVOS", ModuloActivos, "🏗️ Activos")
interfaz/menu_lateral.py:25   "activos"
interfaz/menu_lateral.py:315  botón "🏗️ Activos" / "ACTIVOS"
```

**Clasificación: REWRITE** — requiere `assets_routes.py` + registro consistente con otros módulos ya refactorizados.

## 7. Permisos

**Corrección post-auditoría (ASSET-2):** sí existe una entrada `"ACTIVOS"` en `core/security/permission_catalog.py::CANONICAL_MODULE_PERMISSIONS` (línea 361), pero es un stub plano heredado sin granularidad: `["ver", "crear", "mantenimiento"]` — mismo estilo que el `"RRHH"` aún no refactorizado. No hay control de permisos granular real (no hay verbos por custodia, transferencia, work order, inspección, capitalización, inventario físico, baja o etiquetas). ASSET-2 reemplazó este stub en el propio catálogo con la lista granular derivada de `backend/application/assets/permissions.py::AssetPermissions` (~80 códigos `ACTIVOS.*`), siguiendo la misma transformación que COMPRAS/INVENTARIO/FINANZAS ya tuvieron ([[feedback_permissions_compras_standard]]).

## 8. Artefactos previos en `docs/refactor/`

Ninguno. `docs/refactor/` solo contenía fases de Caja (`CASH-*`) antes de esta auditoría. Este es un refactor **desde cero**, no una continuación.

---

## Veredicto de clasificación (resumen)

| Elemento | Clasificación |
|---|---|
| `modulos/activos.py` | REWRITE |
| `core/services/asset_service.py` | REWRITE (split domain/application/infra) |
| `backend/domain/finance/entities/fixed_asset.py` + repo + use cases + query service | PRESERVE (alcance financiero) |
| `asset_commands.py` / `asset_query_service.py` / `create_asset_use_case.py` | REVISAR → probable DELETE_DUPLICATE |
| Tablas `activos`, `mantenimientos`, `activos_depreciacion` | MOVE (migrar datos a esquema canónico) |
| Tablas `assets` / `asset_maintenance` (huérfanas) | DELETE_DUPLICATE — corregido en ASSET-23: solo `asset_maintenance`, `assets` se preserva (consumidor real en Finanzas) |
| Tabla `depreciacion_acumulada` | REVISAR — posible duplicado |
| Tablas `fixed_assets`, `asset_depreciation_entries`, `maintenance_records` | PRESERVE / EXTEND |
| `tests/test_asset_service_ui_reads.py` | PRESERVE como red de regresión |
| Permisos `"ACTIVOS": ["ver","crear","mantenimiento"]` (stub plano) | REWRITE → `AssetPermissions` granular (~80 códigos), hecho en ASSET-2 |
| `assets_routes.py` | BLOCKED — no existe aún, pendiente para la fase de UI Foundations |

---

## Fases ejecutadas — ver el .md dedicado de cada una

A partir de ASSET-1 cada fase tiene su propio documento en `docs/refactor/`, siguiendo la misma convención que las fases `WA-N_*.md` del canal WhatsApp (un archivo por fase, con qué se construyó, decisiones y tests):

- [`ASSET-1_guardrails.md`](ASSET-1_guardrails.md) — 21 tests de arquitectura, incluyendo los 3 que blindan la frontera Activos↔Finanzas.
- [`ASSET-2_permisos.md`](ASSET-2_permisos.md) — `AssetPermissions` (~80 códigos `ACTIVOS.*`), `AssetAuthorizationPolicy`, scopes.
- [`ASSET-3_dominio_base.md`](ASSET-3_dominio_base.md) — agregado `Asset`, `AssetCategory`, `AssetLocation`.
- [`ASSET-4_custodia.md`](ASSET-4_custodia.md) — `AssetAssignment`, `AssetLoan`.
- [`ASSET-5_transferencias.md`](ASSET-5_transferencias.md) — `AssetTransfer` y la regla de segregación de funciones de §84.
- [`ASSET-6_mantenimiento.md`](ASSET-6_mantenimiento.md) — `MaintenancePlan`, `MaintenanceWorkOrder`.
- [`ASSET-7_inspecciones.md`](ASSET-7_inspecciones.md) — `InspectionChecklistTemplate`, `AssetInspection`.
- [`ASSET-8_medidores.md`](ASSET-8_medidores.md) — `AssetMeter`, `AssetMeterReading`.
- [`ASSET-9_documentacion.md`](ASSET-9_documentacion.md) — `AssetDocument`, `AssetWarranty`, `AssetInsurancePolicy`.
- [`ASSET-10_costos_capitalizacion.md`](ASSET-10_costos_capitalizacion.md) — `AssetImprovement`, `AssetCapitalizationProposal`.
- [`ASSET-11_inventario_fisico.md`](ASSET-11_inventario_fisico.md) — `AssetPhysicalInventory`, `AssetPhysicalInventoryLine`, `AssetPhysicalDiscrepancy`.
- [`ASSET-12_bajas.md`](ASSET-12_bajas.md) — `AssetDisposalRequest`, `AssetDisposal`.
- [`ASSET-13_etiquetas_qr.md`](ASSET-13_etiquetas_qr.md) — `AssetTag`.
- [`ASSET-14_query_services.md`](ASSET-14_query_services.md) — `AssetDirectoryQueryService` y 5 más, sobre Protocol ports.
- [`ASSET-15_integraciones.md`](ASSET-15_integraciones.md) — `SupplierLookupPort`, `EmployeeLookupPort`, `DeviceRegistrationLookupPort`, `DocumentStorageGatewayPort`, `PrintJobGatewayPort`.
- [`ASSET-16_ui_foundations.md`](ASSET-16_ui_foundations.md) — `frontend/desktop/modules/assets/` (rutas, presenter, workspace).
- [`ASSET-17_dashboard.md`](ASSET-17_dashboard.md) — `AssetsOverviewPage`.
- [`ASSET-18_directorio_detalle.md`](ASSET-18_directorio_detalle.md) — `AssetsDirectoryPage`, `AssetDetailPage`.
- [`ASSET-19_maintenance_ui.md`](ASSET-19_maintenance_ui.md) — `WorkOrdersBoardPage` (solo lectura), `MaintenanceAgendaPage`.
- [`ASSET-20_responsive_touch.md`](ASSET-20_responsive_touch.md) — verificación de resoluciones + accesibilidad (sin sistema de densidad táctil formal).
- [`ASSET-21_offline.md`](ASSET-21_offline.md) — `AssetSyncConflict` (vocabulario de dominio, sin motor de sincronización real).
- [`ASSET-22_migracion_consumidores.md`](ASSET-22_migracion_consumidores.md) — audit de consumidores reales del legacy (job de depreciación mensual, `treasury_service.py`).
- [`ASSET-23_reporte_disposicion_legacy.md`](ASSET-23_reporte_disposicion_legacy.md) — tabla de disposición §115, **corrige ASSET-0**: la tabla `assets` no está huérfana.
- [`ASSET-24_validacion_final.md`](ASSET-24_validacion_final.md) — checklist honesto contra §113, cierre de la pipeline.

**Pipeline ASSET-0 a ASSET-24 completa** (2026-09-02, sesión única con múltiples continuaciones). 228 tests en verde, cero regresiones en el legacy, dominio EAM completo con reglas de negocio reales (no solo estructura), UI de solo lectura funcional de punta a punta. **La capa de persistencia/escritura nunca se construyó** — ver `ASSET-24_validacion_final.md` para el checklist honesto de qué está y qué no está hecho, y por qué.
