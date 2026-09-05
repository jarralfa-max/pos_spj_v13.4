# ASSET-1 — Guardrails de arquitectura (Activos / EAM)

Ejecutado: 2026-09-02. §110 del prompt maestro (`docs/refactor/assets_legacy_inventory.md` es la auditoría ASSET-0 que motiva estas reglas; `docs/refactor/assets_finance_boundary_map.md` es el contrato de frontera que la mitad de estos tests existe para blindar).

## Qué se construyó

`tests/architecture/assets_guardrails.py` — scanner compartido, mismo patrón ratchet que `customers_crm_guardrails.py`: define las rutas canónicas (`ASSET_DOMAIN_ROOT`, `ASSET_APPLICATION_ROOT`, `ASSET_INFRA_REPO_ROOT`, `ASSET_UI_ROOT`, `ASSET_SCHEMA_FILE`, `ASSET_ROUTES_FILE`, `ASSET_PERMISSIONS_FILE`) y dos listas de vigilancia: `LEGACY_ASSET_FILES` (`modulos/activos.py`, `core/services/asset_service.py`) y `ORPHANED_ASSET_SCAFFOLDING` (los 3 archivos huérfanos detectados en ASSET-0).

Se agregó `ASSETS_MODULE_ALLOWLIST: dict = {}` a `tests/architecture/allowlists.py` — el bounded context nuevo no tolera ninguna excepción de guardrail desde el día uno.

21 archivos de test (`test_assets_*.py` / `test_asset_*.py`):

| Test | Qué verifica |
|---|---|
| `test_assets_ui_has_no_sql.py` | Sin SQL embebido en `frontend/desktop/modules/assets/` |
| `test_assets_ui_has_no_repositories.py` | La UI no importa repositorios directamente |
| `test_assets_ui_does_not_receive_app_container.py` | Sin `AppContainer`/`container.db` en la UI |
| `test_assets_use_uuidv7.py` | Sin `AUTOINCREMENT`/`INTEGER PRIMARY KEY`/`lastrowid`/`uuid4()` |
| `test_assets_have_no_integer_identity.py` | AST: ningún campo `id`/`*_id` tipado como `int` |
| `test_assets_use_decimal.py` | AST: sin `float`, sin columnas `REAL` |
| `test_assets_do_not_post_journal_entries.py` | **Sin `PostingEngine`/`registrar_asiento`/cuentas contables hardcodeadas** |
| `test_assets_do_not_execute_treasury_payments.py` | **Sin `treasury_service.*()`/`registrar_gasto_opex`/`completar_y_pagar`** |
| `test_assets_do_not_own_financial_depreciation.py` | **Sin recálculo de depreciación financiera** (`monthly_depreciation`, `net_book_value`, etc.) |
| `test_assets_maintenance_does_not_write_finance.py` | Archivos de mantenimiento no llaman a Finanzas |
| `test_assets_parts_do_not_write_inventory.py` | Sin descuento directo de stock |
| `test_assets_use_design_system.py` | Sin imports de `modulos.ui_components`/`design_tokens`/`spj_styles` |
| `test_assets_have_no_inline_styles.py` | Sin `setStyleSheet(` |
| `test_assets_have_no_hardcoded_colors.py` | Sin colores hex |
| `test_assets_have_no_emoji_icons.py` | Sin emojis |
| `test_assets_have_no_qtablewidget.py` | Sin `QTableWidget`/`QTabWidget`/`QGroupBox`/`QDoubleSpinBox` |
| `test_asset_routes_are_registered.py` | `pytest.skip` documentado hasta que exista `assets_routes.py` |
| `test_asset_permissions_are_granular.py` | `ALL_ASSET_PERMISSIONS` ≥ 60, prefijo `ACTIVOS.`, sin fragmentos financieros |
| `test_asset_scopes_are_enforced.py` | `AssetScopeLevel` cubre OWN/ASSIGNED/BRANCH/REGION/COMPANY/ALL |
| `test_assets_have_no_legacy_imports.py` | Sin imports de `modulos.activos`/`core.services.asset_service`/scaffolding huérfano |
| `test_assets_legacy_allowlist_is_empty.py` | `ASSETS_MODULE_ALLOWLIST == {}` |

Las tres marcadas en negrita son el punto central de todo este bounded context: son las que impiden que se repita el acoplamiento que tenía `core/services/asset_service.py` (`completar_y_pagar_mantenimiento()` llamando `treasury_service.registrar_gasto_opex()`, `accrual_depreciacion_mensual()` llamando `finance_service.registrar_asiento()`).

## Iteración necesaria

Un falso positivo: el regex de `test_assets_do_not_execute_treasury_payments.py` matcheaba la palabra `treasury_service` dentro del propio docstring de `events.py` que explica la regla. Se corrigió exigiendo un patrón de llamada real (`treasury_service\s*\.\s*\w+\s*\(`) en vez de la palabra suelta.

## Tests

27 passed, 2 skipped (rutas y schema — intencional, no vacío silencioso) en la primera corrida correcta. Verificado además: `tests/architecture/` completo (~700 archivos) corre con 84 fallas preexistentes no relacionadas (Settings/Transfers/text_pk_not_null/uuidv7_cutover — ver memoria `env_nested_git_repo_pos_spj`), cero fallas nuevas.

## Siguiente fase

ASSET-2 — Permisos/roles/scopes.
