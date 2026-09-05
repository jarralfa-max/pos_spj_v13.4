# ASSET-21 — Offline (Activos / EAM)

Ejecutado: 2026-09-02. §105-106 del prompt maestro.

## Esta fase es vocabulario de dominio, no un motor de sincronización

§105-106 describen un sistema offline-first completo: escritura local con `operation_id`, cola de outbox, estados `LOCAL_PENDING/SYNCING/SYNCED/CONFLICT/FAILED`, y resolución de conflictos sin sobrescritura silenciosa. **Nada de eso se construyó como sistema funcional en esta fase** — construirlo requeriría una conexión real al motor de sincronización que ya existe en este repo (`sync/`, según la arquitectura documentada en `CLAUDE.md`), y Activos no tiene ninguna infraestructura de persistencia (repos concretos, `assets_schema.py`) contra la cual ese motor pudiera operar. Fabricar una cola de escritura local o una UI de "sincronizando…" sin backend real detrás habría sido puro teatro — la misma decisión que ya se tomó en ASSET-19 (tablero de solo lectura en vez de un Kanban falso) y ASSET-20 (no inventar un sistema de densidad táctil).

## Qué sí se construyó

`backend/domain/assets/entities/asset_sync_conflict.py` — `AssetSyncConflict`. El docstring del propio archivo es explícito sobre esta limitación (primera línea: "**This is vocabulary/data-shape only**"). Representa el registro de un conflicto: dos `operation_id` distintos escribiendo al mismo activo antes de poder reconciliarse. **Nunca se resuelve automáticamente** (§106: "No sobrescribir silenciosamente") — `keep_local()`/`keep_remote()`/`resolve_merged()` son las tres únicas formas de cerrar un conflicto, cada una exige un `resolved_by` explícito, y un conflicto ya resuelto no puede resolverse otra vez (`AssetSyncConflictAlreadyResolvedError`).

Nuevos enums: `AssetSyncStatus` (LOCAL_PENDING/SYNCING/SYNCED/CONFLICT/FAILED, §105), `AssetSyncConflictType` (los 6 tipos exactos de §106: ASSET_UPDATED_REMOTELY/CUSTODY_CHANGED/LOCATION_CHANGED/WORK_ORDER_CHANGED/DISPOSAL_STATE_CHANGED/PHYSICAL_COUNT_CONFLICT), `AssetSyncConflictStatus`. Excepciones: `AssetSyncConflictNotFoundError`, `AssetSyncConflictAlreadyResolvedError`. Port: `AssetSyncConflictRepositoryPort` (Protocol, sin implementación — igual que todos los demás ports de Activos).

## Tests

`tests/unit/assets/test_asset_sync_conflict.py` — creación (mismo `operation_id` en ambos lados no es un conflicto real, se rechaza), las tres formas de resolución, resolver dos veces falla, resolución sin resolutor falla.

**Conteo total de la suite de Activos tras ASSET-1 a ASSET-21**: 228 tests (unitarios + arquitectura) passed, 1 skipped (`assets_schema.py` aún no existe) — todo en verde.

## Siguiente fase

ASSET-22 (migrar consumidores) no tiene nada que migrar todavía — no existe ningún consumidor real del nuevo bounded context fuera de este propio módulo. ASSET-23 (eliminación de legacy) sería prematura: `modulos/activos.py` sigue siendo la única implementación funcional de Activos en producción. **El bloqueador de fondo sigue siendo el mismo desde ASSET-6, ahora atravesando 21 fases**: cero infraestructura de persistencia, cero casos de uso de escritura. Todo lo construido en ASSET-3 a ASSET-21 — 30+ entidades de dominio con máquinas de estado completas, reglas de segregación de funciones reales, 6 QueryServices, 5 puertos de integración, y una UI de solo lectura que funciona de punta a punta — es dominio correcto y probado, pero no hay una sola operación de Activos que se pueda ejecutar contra una base de datos real hoy.
