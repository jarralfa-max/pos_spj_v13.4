# CRM-39 — Fase 5: verificación de seguridad/auth/policy (sin brechas nuevas)

Fecha: 2026-08-16. A petición del usuario de retomar "FASE 5 — SEGURIDAD /
AUTH / POLICY". A diferencia de las fases anteriores, esta terminó siendo
una auditoría de verificación, no una fase de construcción — cada
requisito que pide Fase 5 ya estaba resuelto por CRM-2/CRM-3/CRM-25/CRM-29,
confirmado aquí con evidencia directa en vez de asumido.

## Catálogo canónico de permisos

Reverificado con un script directo (no solo memoria de fases previas):
`CustomerPermissions` (84 códigos) y `CRMPermissions` (90 códigos) siguen
en cero divergencia contra `core/security/permission_catalog.py` — ni un
código nuevo de las fases CRM-27 a CRM-38 quedó fuera del catálogo
canónico. Nada que limpiar aquí.

## PermissionEvaluator — único, con wildcard, exhaustivamente probado

`SessionContext.tiene_permiso` (el evaluador real conectado a Clientes/CRM,
reusado también por CRM vía `CustomerSessionPermissionChecker` — ver
`frontend/desktop/modules/customers_crm/composition.py:52-54`, no existe
un `CRMSessionPermissionChecker` separado porque no hace falta: el checker
ya es genérico) soporta código exacto, wildcard de módulo (`"CLIENTES.*"`,
CRM-29) y wildcard global (`"*"`) — 6 tests en
`tests/test_crm_29_session_permission_wildcard.py`. `security/rbac.py` y
`core/services/security_service.py` (los otros dos evaluadores del repo)
siguen sin ser consultados por Clientes/CRM — confirmado de nuevo, no solo
recordado de CRM-29.

## Fail-closed

Verificado en las tres capas:
- `CustomerAuthorizationPolicy.require()`: sin checker → `CustomerConfigurationError`;
  sin `user_id` → `CustomerPermissionDeniedError`; código de permiso
  desconocido → deny; checker deniega → deny; checker aprueba → allow.
- `CustomerSessionPermissionChecker.has_permission()`: sin sesión, sesión
  inactiva, `user_id` no coincide con la sesión, sin sucursal activa, sin
  el permiso → deny en los cinco casos — **6 tests exhaustivos ya
  existentes** en `tests/unit/customers/test_customer_session_permission_checker.py`
  cubren exactamente esta matriz (no hubo que escribirlos, ya estaban).
- `CRMAuthorizationPolicy`: mismo `require()`, mismo checker reusado —
  mismas garantías.

## Data scopes — enforcement real en backend, no solo en frontend

`CustomerDataScopeResolver.resolve_view_scope()` resuelve el axis MÁS
AMPLIO que el usuario tiene otorgado (OWN/TEAM/BRANCH/TERRITORY/
PORTFOLIO/COMPANY); si un axis está otorgado pero falta el dato de
contexto (p.ej. BRANCH sin sucursal activa), lanza
`CustomerConfigurationError` — nunca cae a "sin filtro" en silencio.
Confirmado que `CustomerProfileQueryService.get_profile()`/
`list_directory()` lo invocan en cada lectura real, y que `get_profile`
además revalida que el cliente encontrado caiga dentro del scope resuelto
— un usuario no puede sortear el filtro adivinando un `customer_id`.

## Field security — masking real, no solo ocultar widgets en la UI

`FieldVisibility`/`mask()` (campos sensibles: teléfono, correo, RFC, CURP,
dirección, saldo, límite de crédito, notas privadas, documentos,
evidencia de consentimiento) tiene consumidores reales confirmados:
`customer_credit_query_service.py` (montos de crédito),
`service_case_query_service.py`, `crm_note_query_service.py` (notas
privadas) — la decisión de cuánto mostrar se resuelve en el backend según
el permiso del usuario, con default fail-safe a `MASKED` para cualquier
estado no reconocido.

## Limpieza incidental

Se encontró y eliminó `backend/application/customers/permissions.py.tmp.14452.b71727fb8b57`
— un archivo temporal huérfano de una escritura atómica interrumpida de
una sesión anterior (fechado antes de esta sesión), con una versión
desactualizada de `permissions.py` sin las adiciones de §49-55. No era
importable (nombre de archivo inválido como módulo Python) ni referenciado
por nada — basura de repo, no código muerto en el sentido de Fase 9.

## Verificación

```bash
python -m pytest tests/unit/customers/test_customers_security.py \
  tests/unit/crm/test_crm_security.py \
  tests/unit/customers/test_customer_session_permission_checker.py \
  tests/architecture/test_session_permissions_are_normalized.py \
  tests/integration/test_session_permissions_uuid.py \
  tests/test_crm_29_session_permission_wildcard.py -v
```
62 tests pasando, todos preexistentes — ningún test nuevo fue necesario
porque no se encontró ninguna brecha real que cerrar.

## Conclusión

Fase 5 no requería trabajo de construcción para Clientes/CRM: el trabajo
ya estaba hecho desde CRM-2/CRM-3, extendido correctamente por CRM-25/CRM-29,
y esta verificación lo confirma con evidencia directa en vez de darlo por
sentado. El único cambio de esta fase fue eliminar un archivo temporal
huérfano.
