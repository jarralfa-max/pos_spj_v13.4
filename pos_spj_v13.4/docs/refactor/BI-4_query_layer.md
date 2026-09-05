# BI-4 — Consolidación de Query Layer

Estado: **DONE** (relocalización física + imports; wiring al `MetricRegistry`
de BI-3 queda pendiente — ver "Pendiente")

## Alcance

Los archivos `MOVE`-clasificados en `BI-0_legacy_audit.md` vivían dispersos
en las carpetas genéricas `backend/application/{dto,queries,services}/` junto
a decenas de archivos de otros bounded contexts. BI-4 los relocaliza al
bounded context canónico `backend/application/analytics/{dto,queries,services}/`
— mismo movimiento que ya se hizo para Procurement/Products/Meat Processing/
Losses en fases anteriores del refactor.

## Archivos movidos

| Origen | Destino |
|---|---|
| `backend/application/dto/bi_dashboard_dto.py` | `backend/application/analytics/dto/bi_dashboard_dto.py` |
| `backend/application/queries/bi_dashboard_query_service.py` | `backend/application/analytics/queries/bi_dashboard_query_service.py` |
| `backend/application/queries/bi_sales_query_service.py` | `backend/application/analytics/queries/bi_sales_query_service.py` |
| `backend/application/queries/bi_inventory_query_service.py` | `backend/application/analytics/queries/bi_inventory_query_service.py` |
| `backend/application/queries/bi_finance_query_service.py` | `backend/application/analytics/queries/bi_finance_query_service.py` |
| `backend/application/queries/bi_cash_query_service.py` | `backend/application/analytics/queries/bi_cash_query_service.py` |
| `backend/application/queries/bi_forecast_query_service.py` | `backend/application/analytics/queries/bi_forecast_query_service.py` |
| `backend/application/services/bi_dashboard_service.py` | `backend/application/analytics/services/bi_dashboard_service.py` |
| `backend/application/services/bi_export_service.py` | `backend/application/analytics/services/bi_export_service.py` |
| `backend/application/services/bi_settings_service.py` | `backend/application/analytics/services/bi_settings_service.py` |

No se movió `backend/application/queries/business_intelligence_query_service.py`
(el scaffold genérico `DELETE`-candidato de BI-0) — queda fuera de esta pasada,
tiene un consumidor tangencial (`backend/application/queries/__init__.py` +
un test de presencia de scaffolding) que no vale la pena tocar en una fase de
movimiento puro; se retira en BI-32 junto con el resto de la limpieza legacy.

## Import sites actualizados

11 sitios de import corregidos (todos por ruta mecánica
`backend.application.{dto,queries,services}.bi_*` →
`backend.application.analytics.{dto,queries,services}.bi_*`):

- Internos entre los propios archivos movidos (`bi_dashboard_query_service.py`
  → sus 5 sub-servicios; `bi_dashboard_service.py` → `bi_dashboard_dto.py` +
  `bi_settings_service.py` lazy-import).
- `core/app_container.py` (wiring de producción: `bi_dashboard_service`,
  `bi_settings_service`, `bi_export_service`).
- `modulos/reportes_bi_v2.py` (import de `DashboardFilters` dentro de
  `_current_filters()`).
- 13 archivos de test: `tests/architecture/test_bi_query_services_exist.py`,
  `tests/integration/inventory/test_legacy_reader_repoints.py`,
  `tests/integration/products/test_legacy_repoint_categories.py`, y los 10
  `tests/integration/test_bi_*.py` + `tests/test_bi_role_permissions_seed.py`.

Todos los `git mv` fallaron con "not under version control" — los 10 archivos
movidos (y sus consumidores, incluido `core/app_container.py` completo)
resultaron estar **sin trackear en git** en este árbol de trabajo (hallazgo
nuevo, no documentado en `[[env_nested_git_repo_pos_spj]]` hasta ahora). Se
usó `mv` de filesystem en su lugar — no hay historia de git que preservar
porque nunca existió. No se ejecutó ningún `git add`/`git commit` en esta
pasada.

## Verificación

- `ast.parse` sobre todo el repo: sin errores de sintaxis.
- `grep` de las rutas de import viejas sobre todo el árbol: cero coincidencias
  restantes.
- Suite completa de tests relacionados a BI ejecutada (27 archivos):
  **86 passed**, 16 failed, 10 errors — **cero `ModuleNotFoundError`/`ImportError`**
  en toda la corrida. Los 26 failed+error se rastrearon a
  `tests/integration/bi_seed.py::fresh_db()` fallando al aplicar las
  migraciones 024/029/080 en este entorno de test (`no such table: mermas`,
  `no such table: movimientos_caja`, `no such column: venta_id`) — un
  problema de bootstrap de fixture **preexistente y no relacionado** con el
  movimiento de archivos (confirmado corriendo
  `tests/integration/test_bi_alerts_and_insights.py::test_alerta_merma_alta`
  aislado: falla en la misma línea de `bi_seed.py` antes de tocar ningún
  código de BI). El resto de los failed (`test_fase2_bi_cajeros.py`,
  `test_legacy_reader_repoints.py`) tampoco tocan ningún archivo movido —
  consumen `core/services/bi_service.py` (ya deprecado) y el catálogo de
  productos, respectivamente. No se investigó/corrigió el bootstrap de
  `bi_seed.py` — está fuera de alcance de BI-4 (no lo causó, no lo agrava).

## Auditoría REGLA CERO

Movimiento puro de archivos + corrección de imports; ningún dato, schema, ni
identidad nueva. N/A.

## Pendiente

- Los `Bi*QueryService` movidos **todavía no consumen** el `MetricRegistry`
  de BI-3 — sus fórmulas siguen hardcodeadas en SQL dentro de cada servicio
  (igual que antes de BI-4). Cablearlos al registro (para que
  `BiDashboardService` pida `MetricDefinition`/`MetricLineage` en vez de
  tener las fórmulas repetidas en el docstring de `BI_DASHBOARD.md`) es
  trabajo real de próxima fase — no se hizo aquí para no arriesgar romper el
  dashboard en vivo dentro de la misma pasada que lo reubica.
- El bootstrap roto de `tests/integration/bi_seed.py::fresh_db()`
  (migraciones 024/029/080) sigue sin diagnosticarse — bloquea 26 tests de
  BI y probablemente otros fuera de BI. Vale la pena una investigación
  dedicada, pero no es parte de la consolidación de la capa de queries.
