# PROC-1 — Seguridad: Procesamiento Cárnico

Estado: **DONE** (capa de seguridad base; sin Use Cases ni UI todavía)

> **Corrección de convención (post-implementación inicial):** la primera pasada de
> este documento seguía el patrón de `backend/application/losses/` (códigos planos
> `LOSSES_*` sin registrar en `core/security/permission_catalog.py`). El usuario
> pidió explícitamente seguir el **estándar del módulo de Compras**
> (`backend/application/procurement/` / `backend/application/inventory/`) en su
> lugar: códigos punteados `MODULO.accion` **sí registrados** en el catálogo
> canónico, más una `AuthorizationPolicy` con `require()`/`authorize_exception()`.
> Este documento describe la versión corregida, ya aplicada.

## Alcance

Capa de seguridad reutilizable para todos los Use Cases futuros del bounded
context (PROC-6 en adelante), siguiendo el patrón ya validado en
`backend/application/inventory/` y `backend/application/procurement/` — el
"estándar de Compras" pedido explícitamente por el usuario, no el de Mermas.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/application/meat_processing/permissions.py` | `MeatProcessingPermissions` — catálogo de códigos punteados `PRODUCCION.accion` (formato canónico `MODULO.accion`, igual que `PurchasePermissions`/`InventoryPermissions`). Módulo `PRODUCCION` — la clave ya existente en `interfaz/menu_lateral.py` ("Procesamiento Cárnico" → "PRODUCCION"), reutilizada en vez de crear una clave paralela. |
| `core/security/permission_catalog.py` | `CANONICAL_MODULE_PERMISSIONS["PRODUCCION"]` ampliado de `["ver", "ejecutar"]` (stub legacy de 2 acciones) a la lista granular completa (~65 acciones: `orden.*`, `material.*`, `peso.*`, `output.*`, `rendimiento.*`, `reproceso.*`, `empaque.*`, `configuracion.*`, `sacrificio.*`). Es la única fuente de verdad para la matriz de permisos de Configuración → Seguridad. |
| `backend/application/meat_processing/authorization.py` | `MeatProcessingAuthorizationPolicy` — `require()` (falla cerrado sin checker), `has_permission()` (probe no-raise para gating de UI), `authorize_exception()` (autorización en caliente §52, produce un `AuthorizationGrant` auditable, exige que autorizador ≠ solicitante). `PermissionChecker` Protocol + `AllowAll…ForTests`/`DenyAll…ForTests` para pruebas aisladas. Mirror estructural de `InventoryAuthorizationPolicy`. |
| `backend/domain/meat_processing/value_objects/authorization_grant.py` | `AuthorizationGrant` — value object inmutable del registro de auditoría de una autorización en caliente (mirror de `backend/domain/inventory/value_objects/authorization_grant.py`). |
| `backend/application/meat_processing/session_authorization.py` | `MeatProcessingSessionPermissionChecker` — adaptador fail-closed hacia la sesión de escritorio viva (sin cambios respecto a la versión inicial; su forma ya coincidía con `ProcurementSessionPermissionChecker`). |
| `backend/application/meat_processing/execution_context.py` | `MeatProcessingExecutionContext` — alcance de sucursal/almacén (`enforce_branch()`/`enforce_warehouse()`), sin cambios de forma; Compras no tiene un objeto equivalente (usa permisos `ver.sucursal_propia`/`ver.todas_sucursales` directamente), pero mantenerlo no contradice el estándar pedido y sigue siendo útil para los Use Cases de PROC-6+. |

## Por qué `PRODUCCION` y no una clave nueva

`interfaz/menu_lateral.py:306` ya define el botón `"🔪 Procesamiento Cárnico"` con
id de módulo `"PRODUCCION"`, y `migrations/m000_base_schema.py::_seed_system_roles`
ya otorga acciones gruesas (`ver`, `crear`, `editar`, `eliminar`, `exportar`) sobre
esa misma clave a `admin`, `gerente` y `almacen`. Introducir una clave paralela
(`PROCESAMIENTO_CARNICO`) habría violado el principio rector §3/§64 del prompt
maestro ("una sola ruta canónica") y roto la consistencia con el seed de roles
existente. Las acciones granulares nuevas (`orden.crear`, `peso.capturar_manual`,
…) **no se otorgan automáticamente a ningún rol** — deben concederse explícitamente
vía Configuración → Seguridad → Permisos, igual que documenta
`migrations/standalone/177_compras_logistica_canonical_permissions.py` para
Compras/Logística.

## Auditoría REGLA CERO

| Componente | Hallazgo | Estado |
|---|---|---|
| `permissions.py` | Solo constantes `str`; sin ids | ✅ N/A |
| `authorization.py` | Sin persistencia; `authorize_exception()` construye `AuthorizationGrant` con `operation_id` UUIDv7 pasado por el llamador (validación real ocurre en el value object cuando se persista, PROC-3+) | ✅ |
| `session_authorization.py` | Sin persistencia, sin ids nuevos | ✅ N/A |
| `execution_context.py` | No genera identidad; valida `actor_user_id`/`active_branch_id` como strings no vacíos | ✅ |

## Segregación de funciones (§51)

- **A nivel de dominio** (`backend/domain/meat_processing/entities/processing_order.py`,
  PROC-2): `ProcessingOrder.approve()` rechaza si el aprobador creó la orden;
  `ProcessingOrder.reverse()` rechaza si quien revierte cerró la orden.
- **A nivel de autorización en caliente** (este documento):
  `MeatProcessingAuthorizationPolicy.authorize_exception()` rechaza si
  `authorizer_user_id == requested_by`.
- El resto de las reglas de segregación de §51 (pesador vs. autorizador de peso
  manual, quien produce no libera calidad) requieren los Use Cases y entidades de
  fases posteriores (PROC-8/PROC-9/PROC-16) para tener un actor real que comparar.

## Tests

`tests/unit/meat_processing/test_meat_processing_permissions.py` (incluye
verificación catálogo↔permisos: cada código `PRODUCCION.accion` definido en
`MeatProcessingPermissions` tiene su sufijo `accion` presente en
`CANONICAL_MODULE_PERMISSIONS["PRODUCCION"]`),
`test_meat_processing_authorization.py`, `test_meat_processing_session_authorization.py`,
`test_meat_processing_execution_context.py`, y
`tests/architecture/test_meat_processing_permissions_are_granular.py` (verifica
que se reutiliza la clave canónica `PRODUCCION`, que el catálogo dejó de ser el
stub de 2 acciones, y que el dominio no importa módulos legacy).

## Pendiente

- Registrar `MeatProcessingSessionPermissionChecker` +
  `MeatProcessingAuthorizationPolicy` en una futura `MeatProcessingUseCaseFactory`
  (composition root, patrón `InventoryUseCaseFactory`) cuando existan Use Cases
  reales que los consuman (PROC-6+).
- Auditoría de acceso persistente (§62) requiere infraestructura de persistencia
  (PROC-3) — no implementada aquí.
