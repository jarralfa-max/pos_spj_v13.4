# LOSS-1 — Seguridad y permisos de Losses

Estado: `IMPLEMENTED_WITH_TEST_ENVIRONMENT_BLOCKER` (2026-08-01).

## Implementado

- Catálogo granular `LossPermissions`; no define permisos generales `MERMA.*`.
- `LossAuthorizationPolicy` fail-closed con `PermissionChecker` obligatorio.
- `LossExecutionContext` inmutable con actor, sucursal activa, sucursales asignadas y almacenes permitidos.
- Scope por sucursal/almacén y alcance global explícito.
- Límite de aprobación Decimal configurable por llamada; no existe default numérico.
- Autorización en caliente con autorizador distinto al solicitante.
- `LossAuthorizationGrant` auditable con operación, actores, motivo, valor, límite y scope.
- Adaptador a sesión viva que deniega sesión inactiva, actor distinto o sucursal ausente.

## Pruebas agregadas

- `tests/unit/losses/test_loss_authorization.py`
- `tests/unit/losses/test_loss_session_authorization.py`
- `tests/architecture/test_losses_permissions_are_granular.py`

Cubren fail-closed, permisos desconocidos, least privilege, scopes, límite, hot authorization, segregación y rechazo de `float`.

## Validación

- `python -m compileall ...`: PASSED.
- Smoke assertions de autorización real: PASSED.
- Pytest: BLOCKED; Python global y ambos `.venv` no tienen instalado `pytest`.

## Deuda explícita preservada

`modulos/merma.py` sigue usando `MERMA.crear` y `MERMA.autorizar`. No se conectó a la nueva policy porque el comando actual carece del agregado, clasificación, almacén y actor UUID requeridos; hacerlo en LOSS-1 cambiaría el flujo antes de las protecciones de LOSS-2. La prueba de arquitectura mantiene esta deuda visible y debe invertirse durante el cutover, no convertirse en allowlist permanente.

## Gate para LOSS-2

1. Ejecutar las pruebas LOSS-1 con pytest disponible.
2. Definir `LossCase`, estados, clasificaciones y policies Decimal/UUIDv7.
3. Crear comandos con `LossExecutionContext` resuelto desde sesión, nunca IDs confiados desde UI.
4. Integrar autorización en los nuevos use cases; después migrar la UI y eliminar permisos legacy.
