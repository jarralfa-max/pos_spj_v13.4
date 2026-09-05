# ASSET-12 — Bajas (Activos / EAM)

Ejecutado: 2026-09-02. §46-48 del prompt maestro.

## Qué se construyó

`backend/domain/assets/entities/asset_disposal_request.py` — `AssetDisposalRequest` (§46). Nunca cambiar `estado = baja` mediante `UPDATE` directo (§46 lo prohíbe explícitamente) — todo pasa por esta máquina de estados:

```text
REQUESTED → UNDER_REVIEW → APPROVED → IN_PROGRESS → COMPLETED
                          → REJECTED
cualquier estado no terminal → CANCELLED
```

**`approve()` implementa §84 literalmente**: "quien solicita baja no debe aprobarla solo" — lanza `SegregationOfDutiesError` si `approved_by == requested_by`, mismo patrón que `AssetTransfer.receive()` (ASSET-5) y `AssetPhysicalDiscrepancy.approve()` (ASSET-11).

**Pérdida y robo (§48)**: `create()` exige `last_known_location_id` o `last_custodian_user_id` cuando `reason` es `LOSS` o `THEFT` — no se puede reportar una pérdida/robo sin al menos una de las dos evidencias mínimas que pide §48 ("última ubicación", "último custodio").

`backend/domain/assets/entities/asset_disposal.py` — `AssetDisposal` (§46-47, el registro de ejecución física). **Documenta la disposición física únicamente** — nunca calcula valor contable, ganancia/pérdida ni asiento; eso es responsabilidad de `DisposeAssetUseCase` (ya construido y preservado en `backend/application/use_cases/finance/capital_and_asset_use_cases.py`, §47: "Finance administra: valor contable, resultado por venta, asiento").

Nuevos enums: `AssetDisposalReason` (SALE/DONATION/SCRAP/LOSS/THEFT/OBSOLESCENCE/DAMAGE/REPLACEMENT/OTHER), `AssetDisposalRequestStatus`. Excepciones: `AssetDisposalNotFoundError`, `AssetDisposalNotAllowedError`. Eventos añadidos: `ASSET_DISPOSAL_UNDER_REVIEW`, `ASSET_DISPOSAL_CANCELLED` (los otros cuatro de §87 ya existían desde ASSET-3). Ports: `AssetDisposalRequestRepositoryPort`, `AssetDisposalRepositoryPort`.

## Tests

`tests/unit/assets/test_asset_disposal.py` — creación (pérdida sin evidencia falla, pérdida con ubicación conocida ok, robo sin evidencia falla, motivos normales no exigen evidencia), workflow (ciclo completo, solicitante no puede autoaprobar, camino de rechazo, ejecutar antes de aprobar falla, cancelar estado terminal falla), `AssetDisposal` (creación ok, ejecutor requerido).

**Conteo total de la suite de Activos tras ASSET-1 a ASSET-12**: 140 tests (unitarios + arquitectura) passed, 2 skipped (intencional) — todo en verde.

## Siguiente fase

Con ASSET-10/11/12 cerradas, todas las fases de dominio "core" del prompt maestro (§11-48) están construidas salvo etiquetas/QR (ASSET-13). Sigue sin existir infraestructura de persistencia para ninguna de las 12 fases (repository ports son solo `Protocol`, sin `assets_schema.py`, sin repos SQLite concretos, sin `use_cases`/UoW de aplicación) — este pendiente se ha señalado al cierre de ASSET-6, ASSET-9 y ahora ASSET-12. Antes de ASSET-13 (etiquetas/QR) o de seguir hacia QueryServices/Integraciones/UI, es el momento natural para una fase de infraestructura que haga ejecutable todo lo construido hasta aquí.
