# ASSET-2 — Permisos, autorización y scopes (Activos / EAM)

Ejecutado: 2026-09-02. §71-85 del prompt maestro.

## Decisión de convención — dotted codes, no `ASSETS_VIEW`

El prompt maestro sugiere permisos estilo `ASSETS_VIEW`, `ASSETS_CREATE` (ALL_CAPS, guion bajo). **No se siguió esa sugerencia.** Este repo ya tiene un estándar real y vigente — códigos `MODULO.accion` (punteados, minúsculas en el sufijo) registrados en `core/security/permission_catalog.py::CANONICAL_MODULE_PERMISSIONS`, consumidos de verdad por la UI de matriz de permisos en Configuración → Seguridad → Permisos y por `rol_permisos`/`usuario_permisos` (ver memoria `feedback_permissions_compras_standard` — el usuario corrigió explícitamente este mismo punto para Compras/Cárnico en una fase anterior). Activos sigue ese estándar, no el del prompt maestro.

## Hallazgo de auditoría que cambió el punto de partida

`permission_catalog.py` **no estaba vacío** para `"ACTIVOS"` — tenía un stub plano heredado en la línea 361: `["ver", "crear", "mantenimiento"]` (mismo estilo que el `"RRHH"` aún no refactorizado). ASSET-2 reemplazó ese stub in-place, no creó una entrada nueva.

## Qué se construyó

`backend/application/assets/`:

- **`permissions.py`** — `AssetPermissions`, ~80 códigos `ACTIVOS.*` agrupados por §71-82: acceso general, activos (CRUD + ciclo de vida), custodia, transferencias, mantenimiento (plan + work order + costo), inspección, costo/frontera financiera (`ACTIVOS.costo.ver`, `ACTIVOS.proyeccion_financiera.ver`, `ACTIVOS.capitalizacion.*` — deliberadamente **sin** ningún `ACTIVOS.asiento.*` ni `ACTIVOS.tesoreria.*`), inventario físico, documentación/garantías/seguros, bajas, etiquetas/QR. `ALL_ASSET_PERMISSIONS` vía introspección `vars()`.
- **`authorization.py`** — `AssetAuthorizationPolicy`, fail-closed (mirror del patrón más refinado de Inventory, no el más simple de Compras): `permissive_for_tests()`, `has_permission()` (probe no-raising), `require()` (raise si no hay checker configurado — nunca fail-open), `authorize_exception(authorizer_user_id, requested_by, permission_code)` que exige un autorizador distinto del solicitante (`SegregationOfDutiesError` si son la misma persona — §84). `PermissionChecker` Protocol propio del módulo (no compartido), más `AllowAllAssetPermissionCheckerForTests`/`DenyAllAssetPermissionCheckerForTests`.
- **`result.py`** — `AssetResult` (mismo shape que `ProcurementResult`/`FinanceResult`: `ok()`/`fail()`, `success`/`message`/`operation_id`/`entity_id`/`error_code`/`data`).
- **`scopes.py`** — `AssetScopeLevel` (OWN/ASSIGNED/BRANCH/REGION/COMPANY/ALL, §83), `AssetDataScope` (value object frozen: `level` + `branch_ids` + `custodian_user_id`), `AssetDataScopeResolver` (Protocol — contrato solamente, la implementación concreta llega con los QueryServices en una fase posterior).

`core/security/permission_catalog.py` — la entrada `"ACTIVOS"` reemplazada in-place con la lista granular completa (sufijos, sin el prefijo `ACTIVOS.`).

## Explícitamente fuera de alcance

No se sembraron roles de sistema nuevos (`ASSET_CUSTODIAN`, `ASSET_TECHNICIAN`, etc. — §82). Los permisos granulares nuevos nunca se otorgan automáticamente a roles sembrados (precedente establecido en `migrations/standalone/177_compras_logistica_canonical_permissions.py`) — esto es comportamiento esperado fail-closed, no un pendiente a corregir reflexivamente.

## Tests

Cubierto por `test_asset_permissions_are_granular.py` y `test_asset_scopes_are_enforced.py` (ver `ASSET-1_guardrails.md`) — ambos en verde.

## Siguiente fase

ASSET-3 — Dominio base (Asset/Category/Location).
