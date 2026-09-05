# ASSET-3 — Dominio base (Activos / EAM)

Ejecutado: 2026-09-02. §11-18, §64 del prompt maestro.

## Contradicción arquitectónica resuelta (§2)

`Asset` (el nuevo agregado, `backend/domain/assets/entities/asset.py`) es una entidad **distinta** de `backend.domain.finance.entities.fixed_asset.FixedAsset`, que ya existía y es DDD-limpio (Money VOs, `operation_id`, capitalización/depreciación/disposición). No se fusionan — se correlacionan por id/eventos vía `Asset.financial_asset_id`. Ver `docs/refactor/assets_finance_boundary_map.md` para el mapa completo de propiedad por dominio.

## Qué se construyó

`backend/domain/assets/`:

- **`enums.py`** — `AssetStatus` (DRAFT/AVAILABLE/ASSIGNED/IN_USE/IN_MAINTENANCE/OUT_OF_SERVICE/LOANED/MISSING/DISPOSAL_PENDING/DISPOSED/SOLD/DONATED/STOLEN/LOST), `AssetCondition`, `AssetCriticality`, `AssetOwnershipType`, `AssetWarrantyStatus`, `AssetLocationType`/`AssetLocationStatus`, `AssetCategoryStatus`.
- **`exceptions.py`** — `AssetDomainError` base + ~10 subclases (`AssetNotFoundError`, `AssetStateInvalidError`, `AssetConditionInvalidError`, `AssetCategoryNotFoundError`, `AssetLocationNotFoundError`, `AssetPermissionDeniedError`, `SegregationOfDutiesError`, `DuplicateOperationError`, `InvalidMoneyError`).
- **`events.py`** — `AssetEvents` (~30 constantes cubriendo ciclo de vida/custodia/transferencia/mantenimiento/inspección/capitalización/inventario físico/baja) + `build_event_payload()` (mismo shape que `procurement.events.build_event_payload`: `event_id` nuevo por publicación, `operation_id` para idempotencia/correlación).
- **`repository_ports.py`** — solo `Protocol` (sin implementación): `AssetRepositoryPort`, `AssetCategoryRepositoryPort`, `AssetLocationRepositoryPort`, `ProcessedEventRepositoryPort`, `OutboxRepositoryPort`.
- **`entities/asset.py`** — el agregado `Asset`. Campos clave: `asset_number` (folio comercial, distinto del UUID interno — §13), `operation_id`, `version`, `custodian_user_id`/`responsible_employee_id`/`current_branch_id`/`current_location_id`. Métodos guardados: `create()`, `commission()` (DRAFT→AVAILABLE), `suspend()`/`reactivate()` (↔OUT_OF_SERVICE), `change_condition()`, `change_criticality()`, `relocate()`.
- **`entities/asset_category.py`** — `AssetCategory` (catálogo configurable, nunca hardcodeado en UI — §15).
- **`entities/asset_location.py`** — `AssetLocation` (jerárquica: Empresa→Sucursal→Área→Cuarto→Posición vía `parent_location_id`, obligatorio bajo nivel BRANCH — §18).

## Decisiones de diseño

- Sin clase base compartida para entidades (mismo patrón que `procurement`/`finance`: `@dataclass(slots=True)` plano, `create()` classmethod llamando `new_uuid()` directamente).
- `Money` se importa de `backend.domain.finance.value_objects.money` en vez de duplicarlo — Activos necesita interoperar con `FixedAsset` de todas formas, y una tercera copia divergente de `Money` sería un riesgo de integración (recomendación explícita de la investigación de convenciones hecha antes de escribir código).
- Sin persistencia todavía — los repository ports son solo `Protocol`. La infraestructura concreta (SQLite repos + `assets_schema.py`) queda pendiente para una fase posterior.

## Tests

`tests/unit/assets/test_asset_entity.py` + `test_asset_category_and_location.py` — cubren create/commission/suspend/reactivate/change_condition/relocate y los guards de categoría/ubicación jerárquica. Ver `ASSET-4_custodia.md` para el conteo total (los tests de ASSET-3 se agregaron en la misma pasada que ASSET-4/5/6).

## Siguiente fase

ASSET-4 — Custodia.
