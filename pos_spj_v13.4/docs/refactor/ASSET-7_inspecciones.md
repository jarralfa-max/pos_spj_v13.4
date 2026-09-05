# ASSET-7 — Inspecciones (Activos / EAM)

Ejecutado: 2026-09-02. §37-38, §67 (parcial) del prompt maestro.

## Qué se construyó

`backend/domain/assets/entities/inspection_checklist_template.py` — `InspectionChecklistTemplate` + `InspectionChecklistItem` (§38). Los checklists son configurables, nunca hardcodeados en la UI: `add_item()` exige `choices` cuando `response_type` es `CHOICE`. Nuevo enum `InspectionResponseType` (BOOLEAN/TEXT/NUMBER/PHOTO/SIGNATURE/CHOICE).

`backend/domain/assets/entities/asset_inspection.py` — `AssetInspection` (§37) + `InspectionAnswer` (value object embebido, no tiene repositorio propio — vive dentro de la inspección). `answer()` acumula respuestas antes de cerrar; `record_result()` cierra la inspección una sola vez (`InspectionStateInvalidError` si se intenta dos veces o si se intenta responder después de cerrada). `fail()` es un atajo de `record_result(FAIL, ...)`. `passed()` trata PASS y PASS_WITH_OBSERVATIONS como aprobado. Nuevos enums: `InspectionType` (SAFETY/OPERATIONAL/QUALITY/PREVENTIVE/CALIBRATION/REGULATORY), `InspectionResultStatus` (PASS/PASS_WITH_OBSERVATIONS/FAIL/OUT_OF_SERVICE — el miembro `PASS` se nombró `PASS_` porque `pass` es palabra reservada de Python).

Excepciones nuevas: `InspectionNotFoundError`, `InspectionFailedError`, `InspectionStateInvalidError`. Evento nuevo: `ASSET_INSPECTION_CREATED` (los otros dos, `ASSET_INSPECTION_COMPLETED`/`ASSET_INSPECTION_FAILED`, ya existían desde ASSET-3). Ports: `InspectionChecklistTemplateRepositoryPort`, `AssetInspectionRepositoryPort`.

## Explícitamente fuera de alcance

`CreateWorkOrderFromInspectionUseCase` (§67) es una operación cross-agregado (crea un `MaintenanceWorkOrder` a partir de una inspección fallida) — pertenece a la capa de aplicación, no al dominio, y esa capa todavía no existe para Activos (ver "Pendiente" en `ASSET-6_mantenimiento.md`). `InspectionFailedError` queda declarada para cuando esa capa se construya.

## Tests

`tests/unit/assets/test_asset_inspection.py` — checklist (crear, agregar ítems, CHOICE sin choices falla, activar/desactivar), inspección (responder antes de cerrar, cerrar dos veces falla, responder después de cerrada falla, `fail()`, PASS_WITH_OBSERVATIONS cuenta como aprobado).

## Siguiente fase

ASSET-8 — Medidores.
