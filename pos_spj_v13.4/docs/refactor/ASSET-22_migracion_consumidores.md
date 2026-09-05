# ASSET-22 — Migración de consumidores (Activos / EAM)

Ejecutado: 2026-09-02. §112 del prompt maestro.

## Resultado del audit: no hay nada que migrar, pero sí hay algo que inventariar

El nombre de esta fase en el prompt maestro sugiere mover consumidores del bounded context legacy hacia el nuevo. Eso no aplica todavía — **el nuevo bounded context (`domain/assets`, `application/assets`, `frontend/desktop/modules/assets`) no tiene ningún consumidor real fuera de sí mismo** (nada en Finanzas, Compras, RRHH, Configuración o BI importa código nuevo de Activos). Lo que sí existe, y vale la pena dejar documentado antes de plantear cualquier corte futuro, es el **inventario de quién consume el bounded context LEGACY hoy** — el trabajo real que ASSET-23 (eliminación) tendría que resolver primero.

## Consumidores reales del legacy `modulos/activos.py` / `core/services/asset_service.py`

Búsqueda exhaustiva (`grep` de imports + SQL directo contra `activos`/`mantenimientos`/`activos_depreciacion`) en todo el repo, excluyendo el propio módulo legacy y los guardrails/tests de esta pipeline que verifican su AUSENCIA en el código nuevo:

| Consumidor | Archivo | Qué hace | Bloqueante para eliminar legacy |
|---|---|---|---|
| Wiring de DI | `core/app_container.py:465-466` | Construye `AssetService(db, treasury_service, finance_service)` | Sí — punto de construcción único del servicio |
| **Job programado mensual** | `core/app_container.py:902-917` | `_run_depreciacion()` — corre el día 1 de cada mes (o cada 86400s según el scheduler), llama a `AssetService.accrual_depreciacion_mensual()` para TODAS las sucursales | **Sí, crítico** — una automatización de producción real, no solo UI. Eliminar `AssetService` sin reemplazar este job rompe la depreciación mensual automática. |
| Carga perezosa de UI | `core/ui/module_loader.py:43` | Registra `"activos" → ModuloActivos` en el diccionario de módulos lazy-loaded | Sí — punto de entrada de la UI |
| Menú principal | `interfaz/main_window.py:111,670` | `from modulos.activos import ModuloActivos`, `self._conectar("ACTIVOS", ModuloActivos, ...)` | Sí — wiring del botón de menú |
| **Reportes financieros de producción** | `core/services/finance/treasury_service.py:244,327-328,875-881` | Consultas SQL directas: `SUM(depreciacion_anual/12) FROM activos` (depreciación mensual agregada), `SUM(valor_actual) FROM activos` (valor de activos fijos para balance), `SUM(valor_adquisicion) FROM activos WHERE estado='activo'` (activos fijos brutos para reportes de tesorería) | **Sí, crítico** — Tesorería calcula cifras de balance financiero leyendo la tabla `activos` legacy directamente, sin pasar por ningún servicio. Esta es la dependencia cruzada más seria encontrada: el nuevo dominio de Activos no puede simplemente reemplazar la tabla `activos` sin coordinar con Finanzas/Tesorería, que ya la trata como fuente de verdad para reportes reales. |
| Guardrail de identidad | `tests/architecture/test_clean_birth_guardrails.py:889-918` (`test_activos_tables_are_born_clean_uuid_identity`) | Verifica que `activos`/`mantenimientos` usen UUID desde el nacimiento y que `modulos/activos.py` inserte con `INSERT INTO activos (id, nombre...)` | No bloquea, pero debe actualizarse/retirarse junto con el legacy si algún día se elimina |

## Conclusión para ASSET-23

El hallazgo más importante de este audit es que **`treasury_service.py` (Finanzas/Tesorería, ya en producción) lee la tabla `activos` legacy directamente para reportes reales de balance** — esto es exactamente el tipo de acoplamiento cruzado que el prompt maestro (§2, §33) advierte que no se debe duplicar hacia el nuevo bounded context, pero que **ya existe hoy en la dirección opuesta** (Finanzas leyendo la tabla operativa de Activos, no al revés). Migrar esto no es responsabilidad de Activos — sería una tarea de Finanzas para leer desde `fixed_assets`/`asset_depreciation_entries` (el esquema canónico ya identificado en ASSET-0) en vez de `activos`. Documentado aquí como bloqueante conocido, no resuelto en esta sesión.

## Siguiente fase

ASSET-23 — Eliminación de legacy (reporte de disposición, sin eliminar nada todavía — ver doc propio).
