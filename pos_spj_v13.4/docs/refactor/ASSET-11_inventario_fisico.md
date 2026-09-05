# ASSET-11 — Inventario físico (Activos / EAM)

Ejecutado: 2026-09-02. §44-45 del prompt maestro.

## Qué se construyó

`backend/domain/assets/entities/asset_physical_inventory.py` — `AssetPhysicalInventory` (§44, la campaña de conteo). Máquina de estados: `DRAFT → IN_PROGRESS → REVIEW → COMPLETED`, `CANCELLED` desde cualquier estado no terminal. `accepts_scans()` solo es verdadero en `IN_PROGRESS` — una línea de escaneo no puede registrarse fuera de esa ventana (validación que la capa de aplicación, fase posterior, deberá enforced antes de crear una `AssetPhysicalInventoryLine`).

`backend/domain/assets/entities/asset_physical_inventory_line.py` — `AssetPhysicalInventoryLine` (un escaneo). Exige `asset_id` salvo cuando el resultado es `UNREGISTERED` (activo escaneado que no está en el sistema — §44 lo contempla explícitamente). Nuevo enum `AssetScanResult` (FOUND/MISSING/WRONG_LOCATION/WRONG_CUSTODIAN/DAMAGED/UNREGISTERED).

`backend/domain/assets/entities/asset_physical_discrepancy.py` — `AssetPhysicalDiscrepancy` (§45). El workflow textual del prompt maestro ("Detectada → Revisión → Investigación → Resolución → Aprobación") se implementó literalmente como máquina de estados: `DETECTED → UNDER_REVIEW → INVESTIGATING → RESOLVED → APPROVED`. **Nunca se corrige automáticamente** (§45 lo prohíbe) — cada paso es una llamada explícita. `resolve()` exige notas de resolución no vacías. **`approve()` aplica segregación de funciones**: quien resolvió la diferencia no puede aprobarla (`SegregationOfDutiesError`), mismo patrón ya usado en `AssetTransfer.receive()`.

Nuevo enum: `AssetDiscrepancyStatus`. Excepciones: `AssetPhysicalInventoryNotFoundError`, `AssetPhysicalInventoryConflictError`. Eventos añadidos: `ASSET_PHYSICAL_INVENTORY_CANCELLED` (los otros cinco de §87 ya existían desde ASSET-3). Ports: `AssetPhysicalInventoryRepositoryPort`, `AssetPhysicalInventoryLineRepositoryPort`, `AssetPhysicalDiscrepancyRepositoryPort`.

## Tests

`tests/unit/assets/test_asset_physical_inventory.py` — conteo (ciclo completo, no acepta escaneos antes de iniciar, no completa antes de revisión, cancelar en progreso, cancelar estado terminal falla), línea (FOUND exige asset_id, UNREGISTERED no lo exige, `is_clean()`), diferencia (no se crea para FOUND, workflow completo, quien resuelve no puede autoaprobar, resolver sin notas falla).

## Siguiente fase

ASSET-12 — Bajas.
