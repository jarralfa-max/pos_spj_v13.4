# CRM-29 — RBAC: wildcard de módulo real en el evaluador de permisos

Fecha: 2026-08-16. Tercera fase del cut-over completo (mapa Fase 0 §RBAC).

## Hallazgo

`core/session_context.py::SessionContext.tiene_permiso` — el evaluador
realmente wireado a Clientes/CRM (vía `CustomerSessionPermissionChecker`/
`CRMSessionPermissionChecker`) — solo soportaba código exacto
(`"CLIENTES.VER"`) y wildcard global (`"*"`). No existía ningún wildcard
de módulo (`"CLIENTES.*"`), pese a que el catálogo de permisos
(`core/security/permission_catalog.py`) ya usa consistentemente el
formato `MODULO.accion` en todo el repo — dar de alta un rol con acceso a
"todo Clientes" obligaba a enumerar cada código uno por uno.

También confirmado (auditoría, sin cambios en esta fase): existe un
segundo evaluador completamente independiente, `security/rbac.py`, con su
propio catálogo hardcodeado (`_get_default_permisos` codifica
`"CLIENTES.ver","CLIENTES.editar"` directamente, no derivado de
`CANONICAL_MODULE_PERMISSIONS`). Ninguna ruta de Clientes/CRM lo consulta
— es deuda de otros módulos, fuera del alcance de "Clientes/CRM usa el
catálogo moderno" que pide el prompt; no se tocó.

## Qué se cambió

`SessionContext.tiene_permiso` ahora reconoce tres formas de grant:
código exacto, wildcard de módulo (`"MODULO.*"`) y wildcard global
(`"*"`) — aditivo, no se tocó el significado de ninguno de los dos que ya
existían. `permission_catalog.normalize_permission` (mayúsculas) se sigue
usando igual para las tres comparaciones.

## Verificación

```bash
python -m pytest tests/test_crm_29_session_permission_wildcard.py \
  tests/unit/customers/test_customer_session_permission_checker.py \
  tests/architecture/test_session_permissions_are_normalized.py \
  tests/integration/test_session_permissions_uuid.py -v
```
19 tests pasando (6 nuevos de esta fase + 13 preexistentes, cero
regresiones).

## Explícitamente NO tocado

- `security/rbac.py` (segundo evaluador independiente) — no consultado
  por Clientes/CRM, fuera de alcance de esta fase.
- `core/services/security_service.py`/`core/security/decorators.py`
  (tercer evaluador, cache DB-backed, usado por `require_permission`) —
  tampoco en la ruta de Clientes/CRM.
- Renombrar el catálogo canónico existente (`CLIENTES.*`/`CRM.*`) al
  estilo `CUSTOMERS_EDIT` que sugiere el prompt maestro — el propio prompt
  indica explícitamente no renombrar si ya existe un catálogo canónico
  (CRM-2 ya verificó cero divergencia contra
  `core/security/permission_catalog.py`).
