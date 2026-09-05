# ASSET-14 — QueryServices (Activos / EAM)

Ejecutado: 2026-09-02. §63 del prompt maestro.

## Por qué esto sí se pudo construir sin infraestructura

A diferencia de los use cases de mutación (que necesitan un Unit of Work real para persistir), un QueryService solo necesita depender de los **Protocol** de `repository_ports.py` — ya definidos desde ASSET-3 en adelante. Inyección de dependencias por constructor + duck typing estructural de Python significa que estos servicios son 100% funcionales y testeables hoy, con dobles de prueba en memoria, sin esperar a que exista `assets_schema.py` ni un repositorio SQLite concreto. Cuando una fase de infraestructura futura implemente los ports contra SQLite, estos QueryServices funcionan end-to-end sin cambiar una línea.

## Qué se construyó

`backend/application/assets/queries/dto.py` — DTOs congelados (`@dataclass(frozen=True, slots=True)`): `AssetSummaryDTO`, `AssetDetailDTO`, `AssetDashboardKPIsDTO`, `MaintenanceWorkOrderSummaryDTO`, `WarrantyAlertDTO`, `DisposalRequestSummaryDTO`. La UI (fase futura) solo consume estos DTOs, nunca entidades de dominio directamente (§63).

`backend/application/assets/queries/asset_read_services.py` — un solo archivo con varios QueryServices, mismo patrón de archivo agrupado que `backend/application/queries/finance/finance_read_services.py` ya usa en este repo:

| QueryService | Método principal |
|---|---|
| `AssetDirectoryQueryService` | `list_by_branch()`, `list_all()` — resuelve nombre de categoría/ubicación |
| `AssetDetailQueryService` | `get(asset_id)` — incluye si tiene custodia activa |
| `AssetDashboardQueryService` | `kpis(branch_id=None)` — conteos por `AssetStatus` |
| `MaintenanceWorkOrderQueryService` | `list_open_for_asset()`, `list_by_status()` |
| `AssetWarrantyQueryService` | `list_expiring(within_days=30)` |
| `AssetDisposalQueryService` | `list_pending_review()` |

**Limitación conocida, documentada explícitamente en el propio código**: `AssetDirectoryQueryService` resuelve categoría/ubicación con una consulta N+1 por activo contra los ports (`categories.get(...)`, `locations.get(...)`). Es una forma interina razonable dado que los ports no tienen todavía una implementación real — un repositorio SQLite concreto (fase de infraestructura futura) es libre de implementar `list_by_branch()` con un JOIN eficiente puertas adentro; el contrato del QueryService no cambia.

**No se construyeron** los ~11 QueryServices restantes de §63 (`AssetLocationQueryService`, `AssetCostSummaryQueryService`, `AssetFinancialProjectionQueryService`, `AssetPhysicalInventoryQueryService`, `AssetInspectionQueryService`, `AssetAuditQueryService`, `AssetLookupQueryService`, `MaintenanceCalendarQueryService`, etc.) — se priorizó un subconjunto representativo que cubre directorio/detalle/dashboard/mantenimiento/garantías/bajas; el resto se construye cuando una UI o integración concreta los necesite, siguiendo el mismo patrón ya establecido.

## Tests

`tests/unit/assets/test_asset_read_services.py` — dobles de prueba en memoria (`_FakeAssetRepo`, `_FakeCategoryRepo`, etc., duck-typed contra los Protocol) para cada QueryService: resolución de categoría/ubicación, tolerancia a categoría faltante, detalle de activo inexistente, detección de custodia activa, conteo de KPIs por estado, work orders abiertas, garantías por vencer, bajas pendientes de revisión.

## Siguiente fase

ASSET-15 — Integraciones.
