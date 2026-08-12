# CRM-1 — Guardrails

Fecha: 2026-08-08. Depende de CRM-0 (`docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md`).
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md`.

## Objetivo

Antes de escribir una sola entidad de dominio (CRM-3+), fijar la pared que
impide que el bounded context nuevo repita los problemas encontrados en
CRM-0 (tres implementaciones paralelas de "cliente", SQL en capas que no
deberían tenerlo, sin scopes, permisos planos, mezcla con Fidelidad). Sigue
el mismo patrón ya usado en el repo para otros módulos
(`tests/architecture/test_design_system_guardrails.py`,
`test_inventory_does_not_use_legacy_permissions.py`): los guardrails se
escriben **antes** de que exista el código que gobiernan, para que activen
solos en cuanto ese código aparezca, en vez de auditarse después.

No se tocó ningún archivo legacy en esta fase (`modulos/clientes.py` y
compañía siguen intactos — ver CRM-0). CRM-1 sólo:

1. Crea el esqueleto de paquetes vacíos donde vivirá el código nuevo.
2. Crea los 16 tests de arquitectura pedidos.
3. Registra el allowlist de deuda legacy (separado del allowlist del módulo
   nuevo, que debe permanecer vacío).

## Esqueleto de paquetes creado (vacío, sin lógica)

Siguiendo `customers_crm_master_prompt.md` §10 — cinco sub-bounded-contexts
en domain/application/infra, un solo módulo de UI:

```text
backend/domain/{customers,crm,customer_service,customer_credit,customer_privacy}/
backend/application/{customers,crm,customer_service,customer_credit,customer_privacy}/
backend/infrastructure/db/repositories/{customers,crm,customer_service,customer_credit,customer_privacy}/
frontend/desktop/modules/customers_crm/
```

Cada uno tiene solo un `__init__.py` con un docstring que apunta a la sección
del master prompt que lo llena. `backend/infrastructure/db/schema/customers_crm_schema.py`,
`backend/application/customers/permissions.py` y
`frontend/desktop/modules/customers_crm/customers_crm_routes.py` **no**
existen todavía — se crean en CRM-2/CRM-3/CRM-14 respectivamente; varios
guardrails los detectan automáticamente en cuanto aparezcan.

## Helper compartido

`tests/architecture/customers_crm_guardrails.py` centraliza las rutas
canónicas (`CRM_DOMAIN_ROOTS`, `CRM_APPLICATION_ROOTS`, `CRM_INFRA_REPO_ROOTS`,
`CRM_UI_ROOT`, `CRM_SCHEMA_FILE`, `CRM_PERMISSIONS_FILE`, `CRM_ROUTES_FILE`) y
los helpers de escaneo (`crm_py_files`, `crm_source_text`, etc.), para que los
16 tests no dupliquen la definición de "qué es código CRM". También expone
`LEGACY_CUSTOMER_FILES`, el mismo listado que
`allowlists.CUSTOMERS_CRM_LEGACY_CONSUMERS` documenta con motivo por archivo.

## Los 16 guardrails (`tests/architecture/test_customers_crm_*.py`)

| Test | Qué bloquea | Activo hoy |
|---|---|---|
| `..._ui_has_no_sql` | SQL crudo / `.execute(` en la UI | Sí (ratchet) |
| `..._ui_has_no_repositories` | `sqlite3`, `repositories.*`, `container.db`, `*Repository(` en la UI | Sí (ratchet) |
| `..._ui_does_not_receive_app_container` | `AppContainer` / `conexion.db` en la UI | Sí (ratchet) |
| `..._uses_uuidv7` | Repos que crean filas sin `backend.shared.ids.new_uuid` | Skip hasta CRM-3 (sin repos aún) |
| `..._has_no_integer_identity` | `AUTOINCREMENT`, `lastrowid`, `MAX(id)+1`, `legacy_id`, `int\|str` | Sí (ratchet) |
| `..._uses_decimal_for_credit` | `float` en customer_credit; columnas `REAL` de crédito en el schema | Sí (ratchet) |
| `..._does_not_own_loyalty` | Referencias a `tarjetas_fidelidad`, `CardBatchEngine`, `loyalty_ledger`, etc. | Sí (ratchet) |
| `..._does_not_duplicate_cxc` | Escritura directa a `cuentas_por_cobrar`/`movimientos_credito`; tabla CxC propia en el schema | Sí (ratchet) |
| `..._permissions_are_not_role_names` | `if role == "admin"`; códigos de permiso que son nombres de rol | Ratchet activo + check de códigos skip hasta CRM-2 |
| `..._enforces_data_scopes` | Falta de ejes OWN/TEAM/BRANCH/TERRITORY/PORTFOLIO/COMPANY en el módulo de permisos | Skip hasta CRM-2 |
| `..._uses_canonical_design_system` | `modulos.ui_components`/`modulos.design_tokens`; `QTableWidget`/`QGroupBox`/`QDoubleSpinBox`/`QTabWidget` crudos | Sí (ratchet) |
| `..._has_no_inline_styles` | `.setStyleSheet(` no vacío en la UI | Sí (ratchet) |
| `..._has_no_hardcoded_colors` | Hex `#RRGGBB` y `QColor(r,g,b)` en la UI | Sí (ratchet) |
| `..._has_no_emoji_icons` | Emoji como icono literal en la UI | Sí (ratchet) |
| `..._routes_are_stable` | Rutas fuera de `customers.*`/`crm.*`; `return None`; índice numérico como route_id | Skip hasta CRM-14 (sin `customers_crm_routes.py`) |
| `..._legacy_allowlist_is_empty` | Cualquier excepción registrada en `CUSTOMERS_CRM_MODULE_ALLOWLIST` | Sí (allowlist ya vacío) |

19 passed, 3 skipped (con motivo explícito, nunca un pase silencioso). Los
`skip` no son deuda: son la única forma honesta de expresar "esta regla
todavía no tiene nada que verificar" sin fingir que ya está satisfecha.

## Allowlists (`tests/architecture/allowlists.py`)

Dos diccionarios nuevos, con semántica distinta a propósito:

- **`CUSTOMERS_CRM_MODULE_ALLOWLIST`** — excepciones a estos guardrails
  dentro de las rutas canónicas nuevas. Debe quedar en `{}` siempre;
  `test_customers_crm_legacy_allowlist_is_empty.py` lo hace cumplir.
- **`CUSTOMERS_CRM_LEGACY_CONSUMERS`** — lista de quema (burn-down) de los
  10 archivos legacy identificados en CRM-0 que siguen siendo la ruta de
  producción real de "cliente" hoy. No es una excepción a nada; es
  documentación de qué falta apagar en CRM-21/22. No se enforcea con un test
  todavía (no tiene sentido antes de que exista a qué migrar).

## Verificación

```bash
python -m pytest tests/architecture/test_customers_crm_*.py -v
# 19 passed, 3 skipped
```

Suite completa de `tests/architecture/` corrida sin nuevas regresiones (ver
resultado en el historial de esta fase; toma >2 min por el tamaño de la
suite existente).

## Pendiente (próximas fases)

- **CRM-2 (Seguridad):** crear `backend/application/customers/permissions.py`
  (mirror de `CashPermissions`) con los ejes de scope — activa 2 de los 3
  tests en skip.
- **CRM-3 (Customer Master):** primer código real bajo
  `backend/domain/customers/` y `backend/infrastructure/db/repositories/customers/`
  — activa el guardrail de UUIDv7.
- **CRM-14 (UI Foundations):** `customers_crm_routes.py` — activa el
  guardrail de rutas estables.
