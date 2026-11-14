# SDLC-ARQ-PERM-001 — Plan de implementación

- **Spec:** `items/SDLC-ARQ-PERM-001/spec.md` (aprobado por autopiloto el 2026-11-02)
- **Rama:** `sdlc/sdlc-arq-perm-001` desde `claude/erp-financial-bounded-context-uqxz6b` @ `1c4786a7`
- **Estado:** aprobado por autopiloto (2026-11-02) — pendiente de revisión humana en el PR

## Línea base

Ejecutada en la rama antes de tocar código (sólo `spec.md` comiteado), desde `pos_spj_v13.4/`, con `QT_QPA_PLATFORM=offscreen`, `PYTHONDONTWRITEBYTECODE=1`, `TMP/TEMP=D:\spj_tmp\perm-001`, `-p no:cacheprovider --basetemp=D:\spj_tmp\perm-001\pt\…`.

| Segmento | Comando | Resultado |
|---|---|---|
| Arquitectura | `python -m pytest tests/architecture -q -rfE --tb=line` | ARCH_RESULT |
| Unitarias de Configuración | `python -m pytest tests/unit/configuracion tests/unit/test_apariencia_page.py tests/unit/test_configuracion_ui_workspace.py tests/unit/test_empresa_page_installation_branch.py tests/unit/test_empresa_page_org_structure.py tests/unit/test_feature_flags_page.py tests/unit/test_integraciones_page.py tests/unit/test_notificaciones_page.py tests/unit/test_offline_page.py tests/unit/test_pantalla_cliente_page.py tests/unit/test_usuarios_roles_page.py tests/unit/test_sales_hardware.py -q` | **2 failed, 189 passed** (554 s). Los 2 son los preexistentes de `docs/sdlc/baseline/2026-10-28.md`: `test_feature_flags_page.py::TestFeatureFlagsPageLoadsRealData::test_selecting_a_flag_loads_its_rules` y `::TestFeatureFlagsFullLoop::test_create_request_approve_apply_closes_the_loop` (sin `CONFIGURACION.flag.aprobar`). |
| Integración de las áreas + seguridad | `python -m pytest tests/integration/configuracion tests/integration/appearance tests/integration/feature_flags tests/integration/offline tests/integration/document_output tests/integration/organization/test_org_closure.py tests/integration/meat_processing/test_processing_order_folio.py tests/integration/sales/test_sales_ticket_snapshot.py tests/integration/test_admin_unlocks_locked_user.py tests/unit/security tests/integration/security -q` (con `--deselect` de la prueba nueva) | INTEG_RESULT |
| Regresión nueva (paso 1) | `python -m pytest tests/integration/configuracion/test_configuracion_backend_authorization.py -q` | **2 failed**: `DID NOT RAISE ConfigurationAuthorizationConfigurationError` en ambas — reproduce el hueco. |

Esos archivos son todos los que construyen casos de uso de Configuración, el presentador o la composición (búsqueda de nombres de clase en `tests/`).

## Pasos

| # | Archivo(s) | Cambio | Verificación del paso |
|---|---|---|---|
| 1 | `tests/integration/configuracion/test_configuracion_backend_authorization.py` | Prueba de regresión T0 (criterio 1): `SetIntegrationInstanceCredentialUseCase` y `CreateFeatureFlagUseCase` sin política, con `unwired_fails_closed`, deben fallar cerrados sin escribir. Se comitea con `xfail(strict=True)` porque hoy escriben. | `pytest <archivo>` → 2 xfailed (strict: si pasaran, fallaría) |
| 2 | `backend/application/configuracion/authorization.py`; `tests/unit/configuracion/test_configuracion_action_authorizer.py` | `ConfiguracionActionAuthorizer` (spec, «Nuevo contrato»): actor de la sesión, `claimed_actor`, `require_mapped`, falla cerrada sin política, `for_session`, `permissive_for_tests`. | Pruebas unitarias del autorizador en verde |
| 3 | Los 17 módulos de `backend/application/use_cases/configuracion/` (salvo `ticket_designer_service.py`), `backend/application/use_cases/set_installation_branch_use_case.py`, `ticket_designer_service.py`; `frontend/desktop/modules/configuracion/configuracion_presenter.py` (sólo importar las tablas por acción); pruebas | Cada constructor recibe `authorization=None` → `unwired(ConfiguracionActionAuthorizer)`; `execute` empieza con `require`/`require_mapped`. Tablas por acción movidas junto a su enum; el presentador las importa. Se quita el `xfail` del paso 1. Prueba parametrizada de los 80+2 casos de uso (criterios 3-7). | Paso 1 pasa sin `xfail`; prueba parametrizada en verde; `tests/integration/configuracion` y páginas de Configuración igual que la línea base |
| 4 | `frontend/desktop/modules/configuracion/configuracion_routes.py` | La composición crea `ConfiguracionActionAuthorizer` con la MISMA política y lo pasa con `authorization=` a cada caso de uso, a `SetInstallationBranchUseCase` y a `TicketDesignerService`; los 5 que ya recibían la política pasan a palabra clave. | `tests/integration/configuracion/test_every_configuracion_page_opens.py`, `tests/unit/configuracion`, páginas de Configuración igual que la línea base |
| 5 | `tests/architecture/test_configuracion_use_cases_are_authorized.py` | Guardia (criterio 8): (a) casos de uso con `authorization` + `unwired(` + `require` en `execute`; (b) toda construcción en `configuracion_routes.py` pasa `authorization=`. | Guardia en verde; se comprueba que se pone roja quitando un `authorization=` (prueba negativa sobre texto, dentro de la misma prueba) |
| 6 | `migrations/MIGRATION_LOG.md` | Entrada de trazabilidad sin esquema (CLAUDE.md regla 3). | — |

## Archivos que NO se tocan

- Shims de `CLAUDE.md` (finance/WhatsApp): fuera de alcance.
- `backend/application/use_cases/save_system_setting_use_case.py`, `save_smtp_settings_use_case.py`, `save_payment_provider_settings_use_case.py`, `save_company_profile_use_case.py`: código muerto sin llamador ni servicio (spec, «Situación medida»); su borrado es seguimiento.
- `save_user_use_case.py`, `set_user_active_use_case.py`, `save_role_use_case.py`, `save_role_permissions_use_case.py`, `save_user_permissions_use_case.py`: ya autorizan en backend; sólo cambia cómo los construye la composición.
- `ConfiguracionWorkspaceQueryService` y lecturas: fuera de alcance (escritura).
- `tests/conftest.py`: ya resuelve `unwired()` a `permissive_for_tests()`; no necesita cambios.
- `docs/sdlc/BACKLOG.md`: por instrucción, no se edita.

## Migraciones

Ninguna (spec, «Datos y migraciones»): no se crean ni conceden permisos. El número reservado 358 no se usa.

## Criterio de terminado

| Criterio | Prueba |
|---|---|
| 1 | `tests/integration/configuracion/test_configuracion_backend_authorization.py::test_set_credential_without_policy_fails_closed_and_writes_nothing`, `::test_create_feature_flag_without_policy_fails_closed_and_writes_nothing` |
| 2 | `test_configuracion_backend_authorization.py::test_credential_denied_for_session_without_secret_permission`, `::test_credential_written_for_session_with_secret_permission` |
| 3, 4 | `tests/unit/configuracion/test_configuracion_use_cases_backend_authorization.py` (parametrizada por caso de uso y por acción) |
| 5 | `test_configuracion_use_cases_backend_authorization.py::test_claimed_actor_must_be_session_actor*` |
| 6 | `test_configuracion_use_cases_backend_authorization.py::test_ticket_designer_*` |
| 7 | `test_configuracion_use_cases_backend_authorization.py::test_set_installation_branch_*` |
| 8 | `tests/architecture/test_configuracion_use_cases_are_authorized.py` |
| 9 | Segmentos de la línea base, comparados en `test-report.md` |
