# ASSET-4 — Custodia (Activos / EAM)

Ejecutado: 2026-09-02. §19, §21, §65 (parcial) del prompt maestro.

## Qué se construyó

`backend/domain/assets/entities/asset_assignment.py` — `AssetAssignment` (custodia/responsabilidad, §19). Historial completo: `return_custody()` **cierra** el registro (`returned_at` + `condition_at_return`), nunca lo sobrescribe — el siguiente custodio siempre es un nuevo registro. `create()` exige `employee_id` **o** `user_id` (uno de los dos). Nuevo enum `AssetAssignmentType` (CUSTODY/OPERATION/TEMPORARY_LOAN/SHARED/VEHICLE_ASSIGNMENT).

`backend/domain/assets/entities/asset_loan.py` — `AssetLoan` (préstamos temporales, §21). Distinta de `AssetAssignmentType.TEMPORARY_LOAN` — un préstamo siempre tiene `expected_return_at` y `authorized_by`. `is_overdue()` compara contra la fecha esperada; un préstamo ya devuelto nunca está overdue.

Excepciones nuevas: `AssetAssignmentConflictError`, `AssetLoanNotFoundError`. Eventos nuevos: `ASSET_LOANED`, `ASSET_LOAN_RETURNED` (los eventos de asignación — `ASSET_ASSIGNED`/`ASSET_RETURNED`/`ASSET_CUSTODIAN_CHANGED`/`ASSET_LOCATION_CHANGED` — ya existían desde ASSET-3). Ports nuevos: `AssetAssignmentRepositoryPort`, `AssetLoanRepositoryPort`.

## Explícitamente fuera de alcance

Los use cases de aplicación (`AssignAssetUseCase`, `ReturnAssetUseCase`, `LoanAssetUseCase`, `ReturnLoanedAssetUseCase` — §65) no se construyeron: no hay `backend/application/assets/use_cases/` todavía porque no hay infraestructura de persistencia contra la cual ejecutarlos. Solo dominio.

## Tests

`tests/unit/assets/test_asset_assignment_and_loan.py` — create con employee/user, custodia activa/cerrada, préstamo overdue/no-overdue/devuelto, devolver dos veces falla. Suite completa de Activos (ASSET-3 a ASSET-6 combinados): **50 tests unitarios, 27 guardrails de arquitectura (2 skips intencionales)** — todos en verde.

## Siguiente fase

ASSET-5 — Transferencias.
