# SALES-2 — Seguridad (POS-2 del master prompt)

Fecha: 2026-08-16
Fase anterior: `SALES-1_contrato_visual.md`.

## Alcance ejecutado

Master prompt §67, fase POS-2: "Permisos. Autorizaciones. Segregación. Auditoría. Tests."
Mirrors `backend/application/inventory/{permissions,authorization,session_authorization}.py`
(memoria: "the most refined/current version of this pattern") y el estándar de Compras/
Inventario ya establecido en este repositorio (dotted `MODULO.accion`, no el patrón de Losses —
ver memoria `feedback_permissions_compras_standard`).

## Entregables

**Dominio** (`backend/domain/sales/`):
- `exceptions.py` — `SalesDomainError`, `SalesPermissionDeniedError`,
  `SalesConfigurationError`, `SalesSegregationOfDutiesError`, `InvalidSalesAuditFieldError`.
- `value_objects/authorization_grant.py` — `AuthorizationGrant` (registro de una autorización
  en caliente, Decimal-only, exige `reason`/`authorized_by`/`operation_id`).
- `value_objects/sales_audit_entry.py` — `SalesAuditEntry`, con exactamente el set de campos
  del master prompt §63: `user_id`, `authorized_by`, `operation_id`, `sale_id`, `action`,
  `before`, `after`, `reason`, `branch_id`, `workstation_id`, `device_id`, `occurred_at`.

**Aplicación** (`backend/application/sales/`):
- `permissions.py` — `SalesPermissions` (27 códigos granulares `POS.accion`, mapeados 1:1 desde
  la lista del master prompt §61: acceso, venta, descuentos, pagos, postventa, hardware).
- `authorization.py` — `SalesAuthorizationPolicy` (`require`/`has_permission`/
  `authorize_exception`, fail-closed sin checker), `PermissionChecker` Protocol,
  `AllowAll/DenyAllSalesPermissionCheckerForTests`.
- `session_authorization.py` — `SalesSessionPermissionChecker`, el `PermissionChecker` real
  sobre `SessionContext` (espejo exacto de `CustomerSessionPermissionChecker`).
- `audit.py` — `record_sales_audit_entry(container, entry)`, reutiliza el sink genérico
  `core.services.auto_audit.audit_write` en vez de crear una tabla paralela (ver docstring del
  archivo para el razonamiento — campos sin columna dedicada van a `detalles` como JSON).

**Catálogo** (`core/security/permission_catalog.py`):
- Se **extendió** la clave existente `"POS"` (no se creó una clave paralela `"VENTAS"`) con los
  27 sufijos granulares — misma disciplina que Compras/Inventario/CRM. Los 4 códigos planos
  originales (`ver`/`crear`/`cancelar`/`descuento`) se conservan por compatibilidad.

**Composición** (`core/app_container.py`):
- `self.sales_authorization_policy = SalesAuthorizationPolicy(SalesSessionPermissionChecker(self.session))`
  — primer `PermissionChecker` real para Ventas en este repositorio (antes no existía ninguno,
  igual que Customer Master antes de CRM-25).

**UI** (`modulos/ventas.py`):
- `set_usuario_actual`/nuevo `_tiene_permiso_devolucion` — **reemplaza** el check hardcodeado
  `rol.lower() in {"admin", "gerente"}` (línea 1313 original) por
  `sales_authorization_policy.has_permission(session.user_id, SalesPermissions.RETURN)`,
  fail-closed si falta la policy o la sesión. Cierra el hallazgo P1 de `SALES-0_auditoria.md`
  ("Permisos de Ventas siguen en nombre de rol").

**Tests** (33 nuevos, todos verdes):
- `tests/architecture/test_sales_permissions_are_granular.py` (5) — granularidad, sin
  duplicados, todo registrado bajo `"POS"`, sin clave `"VENTAS"` paralela.
- `tests/unit/test_sales_security.py` (16) — policy (fail-closed sin checker, probe vs.
  require, unknown-code), hot-auth (segregación de funciones, auto-autorización rechazada,
  grant requiere motivo/Decimal), `SalesAuditEntry` (validación de campos requeridos).
- `tests/test_ventas_devolucion_authorization_regression.py` (4) — comportamiento nuevo
  (habilitado/deshabilitado según permiso, fail-closed sin wiring) + guardrail de que el
  literal `{"admin", "gerente"}`/`roles_con_devolucion` no vuelva a aparecer en el archivo.

## Cambio de comportamiento real — acción requerida

**Antes de esta fase**: cualquier usuario con rol `admin` o `gerente` (comparación de string,
sin pasar por el catálogo de permisos) veía el botón Devolución habilitado.

**Después de esta fase**: `admin` sigue viendo el botón habilitado (`SessionContext.tiene_permiso`
ya hace bypass total para `es_admin` — verificado en `core/session_context.py:192`, sin cambios
de esta fase). **`gerente` (y cualquier otro rol no-admin) YA NO lo ve habilitado
automáticamente** — el permiso granular `POS.devolucion` no está seedeado para ningún rol en
`migrations/m000_base_schema.py::_seed_system_roles` (que solo seedea
`'POS': ['ver', 'crear', 'editar']`), siguiendo la misma disciplina deliberada ya usada para
Compras/Logística en la migración 177 ("no auto-grant, un administrador debe otorgar
explícitamente vía Configuración → Seguridad → Permisos").

Esto es intencional y consistente con el resto del repositorio, pero es un cambio de
comportamiento real para cualquier usuario `gerente` en producción — un administrador debe
otorgar `POS.devolucion` (y cualquier otro código granular de `SalesPermissions` que se quiera
restaurar) explícitamente vía el UI de permisos antes de desplegar este cambio, o aceptar que
Devolución queda restringida a `admin` hasta entonces.

## Lo que esta fase NO hizo (honesto, no fabricado)

- No se cablearon los demás botones/acciones de Ventas contra permisos granulares (Suspender,
  Reanudar, Cancelar, descuentos rápidos, pago por método, apertura manual de cajón, etc.) — la
  infraestructura (`SalesPermissions`/`SalesAuthorizationPolicy`) ya cubre esos códigos, pero
  solo Devolución quedó realmente conectado en esta fase. El resto de la UI sigue sin gate de
  permiso alguno (ni el viejo ni el nuevo) — quedan como trabajo pendiente explícito.
- No se implementó ningún flujo de UI para "autorización en caliente" (§26: diálogo que capture
  motivo + credencial de un segundo usuario) — `authorize_exception()` existe y está probado a
  nivel de policy, pero ningún diálogo lo invoca todavía.
- No se creó una tabla dedicada `sales_audit_log` — se reutilizó `audit_logs` vía `audit_write`
  (ver razonamiento en `backend/application/sales/audit.py`). Ningún flujo real de Ventas llama
  todavía a `record_sales_audit_entry` — existe y está probado, pero no está invocado desde
  `modulos/ventas.py` en esta fase (eso requeriría tocar `cobrar_venta`/`finalizar_venta`, fuera
  de alcance — POS-2 es seguridad/permisos, no reescritura del flujo de cobro).
- No se tocó el layout (protegido por SALES-1) ni ningún atajo F6-F12 (siguen decorativos, ver
  `sales_pos_visual_contract.md`).

## Siguiente fase

El master prompt continúa con POS-3 (Dominio: Sale, SaleLine, Totals, Policies, Events, Tests).
Confirmar con el usuario antes de asumir el orden.
