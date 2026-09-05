# ASSET-0 — Mapa de frontera Activos ↔ Finanzas ↔ Tesorería

> Resuelve la contradicción arquitectónica: Activos deja de ser dueño de valor contable, depreciación financiera y asientos. Finanzas ya tiene una porción DDD limpia (`backend/domain/finance/entities/fixed_asset.py`) que se preserva y se convierte en el punto de integración canónico.

## Acoplamientos encontrados hoy (a romper)

| Origen | Llamada | Problema | Reemplazo objetivo |
|---|---|---|---|
| `core/services/asset_service.py::completar_y_pagar_mantenimiento()` | `self.treasury_service.registrar_gasto_opex(...)` | Activos paga directamente vía Tesorería | Evento `MAINTENANCE_COST_CONFIRMED` → Finance/AP decide OPEX vs CAPEX → CxP/Tesorería ejecuta el pago |
| `core/services/asset_service.py::accrual_depreciacion_mensual()` | `self.finance_service.registrar_asiento(...)` | Activos calcula y contabiliza depreciación | `AssetFinancialProjectionQueryService` (solo lectura desde Finanzas); el cálculo/asiento vive en `DepreciationDomainService` (finance) ya existente |
| `core/services/asset_service.py::capitalizar_mantenimiento()` | `UPDATE activos SET valor_adquisicion = valor_adquisicion + ...` | Cambia valor contable por UPDATE directo, sin workflow ni aprobación | `AssetImprovement` → `AssetCapitalizationProposal` (Activos, DRAFT/SUBMITTED) → `CapitalizeAssetUseCase` (ya existe en `backend/application/use_cases/finance/capital_and_asset_use_cases.py`, PRESERVE) → evento `ASSET_CAPITALIZATION_ACCEPTED` |
| `modulos/activos.py` (UI) | `self.container.asset_service.completar_y_pagar_mantenimiento(...)` | UI dispara una operación combinada de dominio+finanzas | UI llama `CompleteMaintenanceWorkOrderUseCase` (Activos, solo evidencia operativa); pago queda fuera del scope de Activos |

## Propiedad por dominio (según prompt maestro §2 y ya reflejado en el código existente)

**Activos es dueño de:** activo físico, clasificación, identificación, ubicación, custodia, responsable, condición física, mantenimiento, órdenes de trabajo, inspecciones, garantías, documentación, medidores, transferencias, inventario físico, etiquetas/QR, baja operativa, evidencia de disposición, mejoras capitalizables **propuestas**.

**Finanzas es dueño de** (ya materializado en `backend/domain/finance/`): valor contable (`FixedAsset` entity), depreciación contable (`DepreciationMethod`, `DepreciationDomainService`), asientos (`PostingEngine`), CAPEX/OPEX contable, ganancia/pérdida por disposición (`DisposeAssetUseCase`).

**Compras es dueño de:** orden de compra, proveedor, recepción comercial, factura — Activos consume vía `SupplierLookupQueryService` (a crear si no existe), nunca administra proveedor maestro.

**RRHH es dueño de:** empleado — Activos consume vía `EmployeeLookupQueryService` (a crear si no existe).

**Inventario es dueño de:** refacciones/consumibles — costos de refacciones en mantenimiento fluyen vía `PartsRequest` → Inventory, Activos no descuenta stock directamente.

## Piezas ya existentes que la nueva capa de Activos debe *consumir*, no reimplementar

- `FixedAsset` (domain/finance) — entidad financiera; el nuevo `Asset` (domain/assets) es una entidad *distinta*, con su propio ciclo de vida operativo, correlacionada por `asset_id`/referencia, no fusionada.
- `CapitalizeAssetUseCase`, `DisposeAssetUseCase`, `RegisterCapitalContributionUseCase` (finance) — Activos los invoca a través de eventos/contratos de aplicación, no los reimplementa.
- `FixedAssetQueryService` — fuente de la proyección financiera de solo lectura que Activos muestra en su tab "Finanzas" del detalle de activo (§94 prompt maestro).

## Eventos de integración a definir (contratos, no implementación en esta fase)

```text
ASSET_REGISTERED
ASSET_COMMISSIONED
ASSET_IMPROVEMENT_COMPLETED
ASSET_CAPITALIZATION_PROPOSED   → Finance escucha, decide
ASSET_DISPOSAL_APPROVED         → Finance calcula ganancia/pérdida
ASSET_DISPOSED
MAINTENANCE_COST_CONFIRMED      → Finance/AP decide OPEX vs CAPEX
```

## Regla de guardrail derivada (para ASSET-1 / tests de arquitectura)

- `tests/architecture/test_assets_do_not_post_journal_entries.py` — ningún módulo bajo `domain/assets`, `application/assets`, `frontend/desktop/modules/assets` puede importar/llamar `finance_service.registrar_asiento` ni `PostingEngine` directamente.
- `tests/architecture/test_assets_do_not_execute_treasury_payments.py` — prohibido invocar `treasury_service.registrar_gasto_opex` (o equivalentes) desde Activos.
- `tests/architecture/test_assets_do_not_own_financial_depreciation.py` — prohibido recalcular depreciación (`valor / vida_util / 12` u otro) fuera de `backend/domain/finance`.
