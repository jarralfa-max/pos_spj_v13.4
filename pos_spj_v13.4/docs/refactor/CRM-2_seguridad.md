# CRM-2 — Seguridad

Fecha: 2026-08-08. Depende de CRM-0 (auditoría) y CRM-1 (guardrails).
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §59-76.

## Objetivo

Antes de que exista una sola entidad de negocio (CRM-3+), dejar construido
todo lo que la autorización de ese código va a necesitar: permisos
granulares, resolución de scopes, segregación de funciones, enmascaramiento
y el molde de auditoría — siguiendo exactamente los patrones ya establecidos
para Inventario/Compras/Cash Register/Products/Transfers en este repo, en
vez de inventar un vocabulario nuevo. No se creó ninguna entidad de dominio
(`Customer`, `Lead`, `Opportunity`, ...) todavía — eso es CRM-3+.

## Decisión de formato de permisos (pendiente desde CRM-1)

El master prompt especifica códigos como `CUSTOMERS.CREDIT.APPROVE`
(mayúsculas, `MODULO.RECURSO.ACCION`). El catálogo canónico de este repo usa
`MODULO.accion` en minúscula con puntos (`CAJA.turno.abrir`,
`INVENTARIO.ajuste.aprobar`), verificado en
`core/security/permission_catalog.py` y en cada `*Permissions` class
existente (`CashPermissions`, `InventoryPermissions`). **CRM-2 adopta la
convención ya establecida en el repo**, no la del prompt literal:
`CLIENTES.credito.aprobar`, `CRM.oportunidades.marcar_ganada`. Es la misma
decisión que ya tomaron Compras/Inventario/Caja/Finanzas; una convención
nueva solo para Clientes/CRM habría creado exactamente el tipo de
fragmentación que el pipeline existe para eliminar.

## Permisos (`backend/application/{customers,crm}/permissions.py`)

Dos catálogos, mirror exacto de `InventoryPermissions`
(`backend/application/inventory/permissions.py`):

- **`CustomerPermissions`** (74 códigos, prefijo `CLIENTES.`) — acceso
  general, clientes (con ejes de scope OWN/TEAM/BRANCH/TERRITORY/PORTFOLIO/
  COMPANY sobre la lectura), contactos, direcciones, datos fiscales,
  **crédito** (§68), **privacidad/consentimiento** (§70), **calidad/
  duplicados/import/export** (§71), auditoría.
- **`CRMPermissions`** (78 códigos, prefijo `CRM.`) — leads (§64),
  oportunidades/pipeline/forecast (§65, con ejes OWN/TEAM), actividades/
  tareas/notas (§66), casos de atención/SLA (§67, con ejes OWN/TEAM),
  segmentación/etiquetas/territorios/carteras/propietario (§69).

Ambos catálogos están registrados en `core/security/permission_catalog.py`
(`CANONICAL_MODULE_PERMISSIONS["CLIENTES"]` y `["CRM"]`), con **cero
divergencia** verificada por comparación automática (los 74+78 sufijos del
catálogo son exactamente los códigos de las clases, ni uno de más ni de
menos). Los 4 permisos legacy (`ver`, `crear`, `editar`, `credito`) se
conservan en `CLIENTES` para no romper `modulos/clientes.py` — código nuevo
no debe autorizar contra ellos.

## Scopes (`backend/application/{customers,crm}/data_scope.py`)

No existía ningún resolver de scope real en todo el repo (CRM-0 §9): CAJA/
INVENTARIO/COMPRAS solo llegaron a definir permisos con sufijo
`ver.sucursal_propia`; nada los convertía en un filtro real. Este es el
primero:

- **`CustomerDataScopeResolver`** — seis ejes (OWN/TEAM/BRANCH/TERRITORY/
  PORTFOLIO/COMPANY). Recibe un `CustomerScopeContext` ya resuelto (no hace
  I/O) y un `PermissionChecker` (mismo Protocol que
  `InventoryAuthorizationPolicy`); devuelve el **scope más amplio** que los
  permisos del usuario permiten. Fail closed: sin permiso → `CustomerScopeError`;
  eje otorgado pero sin dato de contexto (p. ej. BRANCH sin sucursal activa)
  → `CustomerConfigurationError`, nunca un fallback sin filtro.
- **`CRMDataScopeResolver`** — mismo patrón, dos ejes (OWN/TEAM), compartido
  por leads/oportunidades/casos vía el conjunto de permisos que cada llamada
  pasa explícitamente (`LEAD_VIEW_SCOPE_PERMISSIONS`,
  `OPPORTUNITY_VIEW_SCOPE_PERMISSIONS`, `CASE_VIEW_SCOPE_PERMISSIONS`).
  BRANCH/TERRITORY/PORTFOLIO/COMPANY no se replican por entidad — el alcance
  COMPANY del módulo completo lo otorga `CustomerPermissions.VIEW_COMPANY`.

## Roles (`backend/application/customers/role_matrix.py`)

`CRM_ROLE_MATRIX`: los 15 roles sugeridos en §59/§72
(`CRM_VIEWER` … `CRM_ADMINISTRATOR`) mapeados a tuplas de permisos
concretos. **Es dato de referencia/semilla, no un mecanismo de
autorización** — los roles de este repo son filas en
`roles`/`permisos`/`roles_permisos` (`migrations/m000_base_schema.py`),
resueltas en runtime vía `SessionContext.tiene_permiso()`; nunca
`if role == "..."` en código de aplicación (eso es justo lo que
`test_customers_crm_permissions_are_not_role_names.py` prohíbe). Este
módulo es la única fuente que una futura migración de semilla (CRM-14+,
cuando el módulo tenga UI) debe consumir.

La segregación de funciones de §73 está codificada directamente en la
matriz: `CRM_CREDIT_ANALYST` tiene `credito.revisar` pero no
`credito.aprobar`; `CRM_DATA_STEWARD` tiene `importar` pero no
`importar.aprobar`; `CRM_AUDITOR` no tiene ningún permiso mutante. Verificado
con tests (`TestCRMRoleMatrix`).

## Segregación de funciones (`backend/domain/customers/policies/segregation_of_duties_policy.py`)

`CustomerSegregationOfDutiesPolicy`, mirror de
`backend/domain/inventory/policies/segregation_of_duties_policy.py` (pura,
sin I/O). Codifica los pares accionables de §73:

| Regla | Método |
|---|---|
| Quien solicita crédito no aprueba su propia solicitud | `enforce_credit_requester_not_self_approving` |
| Quien propone una fusión no la aprueba solo | `enforce_merge_proposer_not_self_approving` |
| Quien importa no aprueba una importación sensible | `enforce_sensitive_import_approver_distinct` |
| Reasignar cartera/propietario requiere motivo | `enforce_ownership_reassignment_justified` |
| Exportar datos sensibles requiere evidencia | `enforce_sensitive_export_evidenced` |
| Anonimizar no borra auditoría | `enforce_anonymization_preserves_audit` |

Dos reglas de §73 no se codificaron como política de dominio porque no son
comparaciones de actores — son elecciones del catálogo de permisos (ya
resueltas arriba): "administrar permisos no da acceso automático a
sensibles" y "configurar pipeline no autoriza marcar ganada sin permiso".

## Autorización en caliente (`backend/domain/customers/value_objects/authorization_grant.py`)

`CustomerAuthorizationGrant`, mirror de
`backend/domain/inventory/value_objects/authorization_grant.py`. Exige
`authorized_by != requested_by`, `operation_id` y `reason` no vacíos;
`credit_amount` se coacciona a `Decimal` y rechaza `float` explícitamente
(REGLA CERO / §37 "todo importe usa Decimal"). Cubre los casos de §74
(aumento extraordinario de crédito, fusión, exportación sensible,
anonimización, reasignación masiva, override de etapa, cierre/reapertura
protegidos) — todos pasan por este único value object, no por un PIN local
(§74 lo prohíbe explícitamente).

## Enmascaramiento (`backend/domain/customers/value_objects/field_visibility.py`)

`FieldVisibility` (`MASKED`/`PARTIALLY_VISIBLE`/`VISIBLE`/`RESTRICTED`) +
`mask()`, primera implementación de este concepto en el repo (no existía
nada equivalente en ningún bounded context). `SENSITIVE_FIELDS` enumera los
campos de §75 (teléfono, correo, RFC, CURP, dirección, saldo, límite de
crédito, notas privadas, documentos, evidencia de consentimiento). El
value object resuelve *cómo* se ve un valor; que nunca llegue a tooltips/
logs/errores/breadcrumbs (§75) sigue siendo disciplina de la capa UI/logging
que consuma esto — no algo que un value object pueda garantizar por sí solo.

## Auditoría (`backend/domain/customers/value_objects/audit_entry.py`)

`CustomerAuditEntry`, mirror de
`backend/domain/products/value_objects/product_audit_entry.py`, extendido
con `customer_id`, `workstation_id` y `correlation_id` (los tres campos que
§76 pide y que la versión de Products no necesitaba). No reemplaza
`core/services/auto_audit.py::audit_write()` — ese sigue siendo el sink que
usa el código legacy; este value object es la forma en que el código nuevo
(CRM-3+) construye un registro de auditoría antes de persistirlo, con las
mismas invariantes de "acción/entidad/usuario/operation_id obligatorios" que
ya usa Products.

## Verificación

```bash
python -m pytest tests/architecture/test_customers_crm_*.py tests/unit/customers/ tests/unit/crm/ -q
# 66 passed, 1 skipped (routes — espera CRM-14)
```

Guardrails de CRM-1 que estaban en `skip` y ahora están **activos y en
verde** gracias a este trabajo:
- `test_customers_crm_permission_codes_are_not_role_names` — el catálogo
  existe y ningún código es un nombre de rol.
- `test_customers_crm_defines_data_scopes` — el catálogo contiene los seis
  ejes de scope.

Consumidores existentes de `core/security/permission_catalog.py`
re-ejecutados sin regresión: `test_cash_register_security_foundation.py`,
`test_inventory_no_legacy_permissions.py`,
`test_inventory_permissions_are_granular.py`, `test_bi_role_permissions_seed.py`,
`test_permission_matrix_catalog_first.py` (17 passed; el único fallo en ese
lote — `test_losses_permissions_are_granular.py` buscando
`modulos/merma.py`, ya eliminado por el refactor de Merma — es previo y no
relacionado).

## Verificación de integridad del catálogo

`CANONICAL_MODULE_PERMISSIONS["CLIENTES"]` y `["CRM"]` se comparan
automáticamente contra `ALL_CUSTOMER_PERMISSIONS`/`ALL_CRM_PERMISSIONS` en
cada corrida de este documento: 0 códigos faltantes, 0 códigos sobrantes,
74 + 78 = 152 permisos granulares totales.

## Pendiente (próximas fases)

- **CRM-3 (Customer Master):** primeras entidades de dominio
  (`Customer`, `CustomerAccount`, `CustomerContact`, `CustomerAddress`,
  `CustomerTaxProfile`) + `CustomerRepository`. Ahí es donde
  `CustomerAuthorizationPolicy`/`CustomerSessionPermissionChecker` (mirror
  de `InventoryAuthorizationPolicy`/`InventorySessionPermissionChecker`) se
  cablean por primera vez a un caso de uso real, y donde
  `test_customers_crm_uses_uuidv7.py` deja de estar en skip.
- **CRM-14 (UI Foundations):** `customers_crm_routes.py` — activa el último
  guardrail en skip.
- Seed migration que cargue `CRM_ROLE_MATRIX` en
  `roles`/`permisos`/`roles_permisos` — no antes de que el módulo tenga UI
  real que usar esos roles.
