# ASSET-18 — Directorio y detalle (Activos / EAM)

Ejecutado: 2026-09-02. §93-94 del prompt maestro.

## Qué se construyó

`frontend/desktop/modules/assets/pages/assets_directory_page.py` — `AssetsDirectoryPage`, ruta `assets.directory`. `SearchInput` + `SearchableComboBox` (filtro de estado) + `StandardTable`, mismo patrón compuesto que `_directory_base.py` de `customers_crm` usa — **no se extrajo una clase base compartida** porque Activos tiene una sola página de directorio hoy (CRM justificó su base class con 4 páginas casi idénticas simultáneas; extraer antes de un segundo consumidor real sería prematuro). Doble clic en una fila emite `entity_selected(asset_id)`; el workspace decide qué hacer con eso (abre el detalle), la página no navega por sí misma.

`frontend/desktop/modules/assets/pages/asset_detail_page.py` — `AssetDetailPage`, ruta `assets.detail`. **Deliberadamente NO es el `AssetSummaryHeader` con 12 tabs que describe §94** (Resumen/Información/Ubicación/Custodia/Mantenimiento/Inspecciones/Costos/Documentos/Garantía/Movimientos/Finanzas/Auditoría) — es un panel único de solo lectura sobre `AssetDetailDTO` (ASSET-14). Construir 12 tabs cuando 8 de ellas no tienen ningún QueryService detrás (inspecciones, documentos, garantía, proyección financiera, auditoría — ninguno existe todavía) habría significado fabricar pestañas vacías sin nada real que mostrar, peor que un panel honesto con lo que sí existe.

`assets_workspace.py` (ASSET-16) se extendió para wirear ambas páginas: `assets.directory`'s `entity_selected` navega a `assets.detail` y le pasa el id.

## Tests

`tests/unit/assets/test_assets_ui_pages.py::TestAssetsDirectoryPage`/`TestAssetDetailPage`/`TestAssetsWorkspace` — directorio (tabla poblada, estado vacío sin resultados, doble clic emite la señal correcta), detalle (renderiza desde un QueryService falso, estado vacío sin activo seleccionado, estado vacío para un id inexistente), workspace (construye las 36 rutas y navega, seleccionar una fila del directorio abre el detalle con el id correcto, sin `module_view` no construye ninguna ruta).

**Verificación adicional**: se corrieron los guardrails de arquitectura genéricos de todo el frontend (`test_design_system_guardrails.py`, `test_no_commit_rollback_in_frontend.py`, `test_no_external_frontend_backend_imports.py`, `test_no_sql_in_frontend.py`) contra el módulo nuevo — los 4 pasan, confirmando que el módulo de Activos no solo cumple sus propios guardrails (`tests/architecture/test_assets_*.py`) sino los del resto del frontend también.

**Conteo total de la suite de Activos tras ASSET-1 a ASSET-18**: 206 tests (unitarios + arquitectura) passed, 1 skipped (`assets_schema.py` aún no existe) — todo en verde. El skip de rutas de ASSET-1 (`test_asset_routes_are_registered.py`) ahora corre de verdad y pasa, en vez de saltarse.

## Siguiente fase

Con la UI de lectura funcionando de punta a punta (dashboard + directorio + detalle, probados contra QueryServices falsos que respetan exactamente el mismo contrato Protocol que una implementación SQLite real tendría que cumplir), **el bloqueador sigue siendo el mismo que se señaló desde ASSET-6**: cero infraestructura de persistencia, cero casos de uso de escritura. No hay ninguna forma de registrar un activo nuevo, asignar custodia, iniciar una transferencia o completar una orden de trabajo — todo el dominio de mutación construido en ASSET-3 a ASSET-13 sigue sin un punto de entrada invocable. Antes de construir más UI (ASSET-19 Maintenance UI necesitaría un Kanban de work orders que mutan de estado — imposible sin casos de uso reales) o continuar hacia formularios de alta/edición, esta es la fase que de verdad hace falta.
