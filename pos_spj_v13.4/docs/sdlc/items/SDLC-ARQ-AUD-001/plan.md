# SDLC-ARQ-AUD-001 — Plan de implementación

- **Spec:** `items/SDLC-ARQ-AUD-001/spec.md` (aprobado el 2026-10-29, Alfred)
- **Rama:** `sdlc/sdlc-arq-aud-001` desde `sdlc/sdlc-wa-002` @ `8580bb9e` — **no** desde la rama base del README (`claude/erp-financial-bounded-context-uqxz6b`), ver Desviación 0.
- **Estado:** aprobado (2026-10-29, Alfred)

Rutas relativas a `pos_spj_v13.4/`. Las pruebas se corren con cwd = `pos_spj_v13.4/`.

## Desviaciones y huecos del spec (requieren aprobación)

- **Desviación 0 — rama de origen.** La rama base del README no contiene el `intent.md` ni el `spec.md` de este ítem: los commits de planeación (`b01ce748` … `8580bb9e`) viven sólo en `sdlc/sdlc-wa-002`. Bifurcar desde la base dejaría el ítem sin spec. Se bifurcó desde `sdlc/sdlc-wa-002` @ `8580bb9e`. Consecuencia: el PR de este ítem arrastrará esos commits de planeación (y `fe4da8f9 sdlc(build-plan): SDLC-WA-002`) mientras no se fusionen antes en la base. Alternativa si no se aprueba: fusionar primero la planeación a la base y re-bifurcar.
- **Hueco 1 — `workstation_id` en eventos de sesión.** El criterio 1 exige `detalles.workstation_id` no vacío en `USER_SESSION_CREATED`, pero `SessionManager` emite sólo `{user_id, session_id}` (`backend/security/sessions/session_manager.py:66,84,103`) y el spec no lo lista entre los cambios. Propuesta: agregar `workstation_id` (y `branch_id` de la sesión) a los payloads de CREATED/EXPIRED/REVOKED, tomados del `UserSession`. `tests/unit/security/test_session_manager.py:108-109` sólo compara nombres de evento, no rompe.
- **Hueco 2 — actor en recuperación.** `AccountRecoveryService` emite `{user_reference}` (`backend/security/recovery/account_recovery_service.py:72,93-95`), no `username`/`user_id`. Propuesta: el sink usa `user_reference` como `usuario` (truncado a 64, igual que D4) y `entidad='usuario'`. Sin cambio en el servicio.
- **Nota — `frontend/desktop/app.py:518` no se toca.** El spec la lista en «Capas afectadas», pero el contrato 7 pone el respaldo `default_workstation_id()` dentro de `build_authentication_coordinator`, que es el punto único que D3 pide. `app.py` ya llama sin `workstation_id` y hereda el respaldo.

## Línea base
Ejecutada el 2026-10-29 sobre `8580bb9e` antes de tocar código (cwd `pos_spj_v13.4/`):

| Comando | Resultado |
|---|---|
| `python -m pytest tests/integration/security tests/unit/security tests/unit/bootstrap tests/integration/bootstrap tests/integration/shared/test_audit_trail.py tests/integration/shell -q` | **655 passed**, 0 failed (7 min 47 s) |
| `QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_authentication_coordinator.py -q` | 12 passed |
| `QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_login_window.py -q` | 7 passed |
| `python -m pytest tests/architecture -q` | **22 failed, 879 passed, 1 skipped, 2 xfailed** (28 min 22 s). Medido en la rama `sdlc/sdlc-arq-aud-001` con el código idéntico a `8580bb9e` (ejecución lanzada por la sesión de plan; quedó como `BASELINE_ARCH` y se completó en Build). Nombres abajo. |

Fallos previos de `tests/architecture` (línea base, por nombre):
`test_clean_birth_guardrails::test_services_repositories_ui_do_not_create_schema` ·
`test_design_system_guardrails::test_desktop_visual_debt_does_not_grow` ·
`test_design_system_guardrails::test_visual_debt_baseline_is_exact_and_kept_pruned` ·
`test_expiry_damage_contract::test_loss10_schema_and_inventory_boundary_are_explicit` ·
`test_inventory_does_not_use_legacy_permissions::test_inventory_does_not_use_legacy_permissions` ·
`test_no_deprecated_services_with_business_logic::test_no_deprecated_services_with_business_logic` ·
`test_no_entity_combo_mass_loading::test_no_qcombobox_mass_loading_for_entities` ·
`test_no_hardcoded_numeric_defaults_in_ui::test_no_hardcoded_numeric_defaults_in_ui` ·
`test_no_hardcoded_paths::test_no_loose_relative_paths` ·
`test_no_legacy_imports::test_no_forbidden_root_namespace_imports` ·
`test_no_raw_sqlite_connect::test_no_raw_sqlite_connect_outside_pool` ·
`test_no_schema_changes_outside_migrations::test_no_create_or_alter_table_outside_migrations` ·
`test_pricing_ui_has_no_database_access::test_pricing_ui_has_no_database_access` ·
`test_products_integration_boundaries::test_dtos_have_no_price_or_stock_fields` ·
`test_refactor_orchestrator` (4: `parent_orchestrator_does_not_call_codex_sdk_directly`, `cli_supports_timeout_and_retry_controls`, `runs_each_turn_in_fresh_subprocess`, `times_out_and_terminates_worker_tree`) ·
`test_refactor_paths_inside_package::test_refactor_directories_are_inside_real_package` ·
`test_refactor_state_json_is_valid::test_done_modules_are_complete` ·
`test_uuidv7_cutover_protection::test_uuidv7_cutover_forbidden_identity_patterns_do_not_increase` ·
`test_whatsapp_runtime_imports::test_channel_uses_qualified_imports`.

Los fallos previos se identifican por **nombre**; cualquier comparación posterior es contra este conjunto, no contra el conteo.

## Pasos

Cada paso termina con su verificación y un commit `<tipo>(seguridad): … [SDLC-ARQ-AUD-001]`.

| # | Archivo(s) | Cambio | Verificación del paso |
|---|---|---|---|
| 1 | `tests/integration/bootstrap/test_site_access_rule_regression.py` (nuevo) | **R1** (regresión, antes de extraer): con `make_db()` fija la respuesta actual de `ApplicationContextBuilder.build()` en 4 casos — ancla cubierta (construye), ancla no cubierta (`SiteAccessDeniedError` con nombre de sucursal), sin ancla (usa sucursal propia, construye), resolver sin soporte de ámbitos (construye). | Pasa sobre código sin cambios. |
| 2 | `tests/unit/security/test_account_lockout_policy.py` | **R2**: `invalid_password` × 4 seguido de éxito → sin bloqueo; y × 5 → bloqueo (fija «éxito corta la racha»). | Pasa sobre código sin cambios. |
| 3 | `backend/security/authentication/errors.py`, `backend/bootstrap/application_context_errors.py` | Mover `SiteAccessDeniedError` a `errors.py` y agregar `SiteDenial(site_id, site_name)` congelado. `application_context_errors.py` lo re-exporta (`from backend.security.authentication.errors import SiteAccessDeniedError`). | R1 + `tests/ui/test_authentication_coordinator.py` + `tests/integration/security/test_contextual_permissions.py` verdes sin cambiar imports. |
| 4 | `backend/bootstrap/application_context_builder.py`, prueba del paso 1 | Extraer `site_access_denial(credentials) -> SiteDenial \| None` (cuerpo actual de `:76-83`); `build()` lo llama y lanza igual. R1 se duplica contra el método extraído (los 4 casos). | R1 (ambas variantes) + `tests/integration/bootstrap` verdes. |
| 5 | `backend/security/sessions/account_lockout_policy.py`, `tests/unit/security/test_account_lockout_policy.py` | `NEUTRAL_FAILURE_REASONS = frozenset({"site_access_denied"})`; `_trailing_failure_streak` salta esos intentos (ni suman ni cortan). Pruebas: 5 × `site_access_denied` → sin bloqueo; 4 × `invalid_password` + 1 neutral + 1 `invalid_password` → bloqueo. | R2 y suite de la política verdes. |
| 6 | `backend/infrastructure/db/repositories/security/security_audit_sink.py` (nuevo), `tests/integration/security/test_security_audit_sink.py` (nuevo) | `SqliteSecurityAuditSink` + `build_security_audit_sink(conn)` según contrato 1 del spec, escribiendo vía `SqliteAuditLogRepository.record(module="SEGURIDAD", …)`; `detalles` = JSON redactado (lista negra + `redact_mapping`); conjunto explícito de no persistidos `{APPLICATION_CONTEXT_CHANGING, NAVIGATION_CONTEXT_REBUILT}`; `usuario` = `user_id` › `username` › `user_reference` truncado a 64 (Hueco 2). Pruebas: mapeo de columnas por familia de evento, criterio 11 (claves sensibles eliminadas), criterio 12 (evento desconocido persistido), no persistidos, `sucursal_id` desde payload › ancla › NULL, `recent()` devuelve la fila. | Nueva suite verde. |
| 7 | `backend/security/sessions/session_manager.py` | Hueco 1: payloads de CREATED/EXPIRED/REVOKED incluyen `workstation_id` y `branch_id` de la sesión. | `tests/unit/security/test_session_manager.py` verde. |
| 8 | `backend/security/authentication/authenticate_user_use_case.py`, `tests/integration/security/test_authenticate_user_use_case.py` (casos nuevos) | Contrato 2: puerto opcional `site_access_check`; denegación → FAILED `site_access_denied` + `USER_AUTHENTICATION_FAILED` con `site_id`/`user_id` + `SiteAccessDeniedError`, sin sesión; intento durante bloqueo → `USER_AUTHENTICATION_FAILED account_locked` y relanza, sin fila de intento; todos los payloads con `workstation_id` y `occurred_at`. Pruebas con sink real sobre `make_db()`: criterios 2, 3, 4, 5. | 13 pruebas existentes sin cambios + nuevas verdes. |
| 9 | `backend/security/authentication/verify_authorizer_credentials_use_case.py`, `backend/api/mobile_credentials.py`, `tests/integration/security/test_verify_authorizer_credentials.py` | Contrato 5: `build_authorizer_credentials_verifier(connection, *, purpose="authorizer")` cablea el sink; el caso de uso usa `purpose` y audita el intento durante bloqueo; `mobile_credentials.py:36` pasa `purpose="mobile"`. Pruebas: criterio 8. Los 5 llamadores de escritorio no cambian (usan el valor por defecto). | Suite del verificador verde. |
| 10 | `backend/bootstrap/application_context_events.py`, `backend/bootstrap/application_context_service.py`, `tests/unit/bootstrap/test_application_context_service.py`, `tests/integration/bootstrap/test_context_switch_audit.py` (nuevo) | Contrato 6: `APPLICATION_CONTEXT_SWITCH_DENIED` emitido antes de cada uno de los 4 `raise` con `reason` (`missing_permission`, `open_operations`, `branch_not_found`, `site_not_covered`). Única expectativa existente que cambia: `test_only_changing_event_emitted_when_permission_denied` (`:111`) → `[CHANGING, SWITCH_DENIED]` (D5). Prueba nueva con sink real: criterio 9. | Suite de bootstrap verde. |
| 11 | `frontend/desktop/shell/desktop_shell_authentication_composition.py`, `frontend/desktop/auth/login_window.py` | Contrato 7: respaldo `default_workstation_id()`; un único `build_security_audit_sink(connection)` pasado a `SessionManager`, `AuthenticateUserUseCase` (+ `site_access_check=ApplicationContextBuilder(connection).site_access_denial`), `AccountRecoveryService` y `ProvisionInstallationUseCase`. `LoginWindow._on_login`: `except SiteAccessDeniedError` → `_show_error`. | `tests/ui/test_authentication_coordinator.py`, `tests/ui/test_login_window.py` y `tests/integration/bootstrap/test_composition_root_real_wiring.py` verdes. |
| 12 | `tests/integration/security/test_security_audit_production_wiring.py` (nuevo), `tests/ui/test_login_window_site_denied.py` (nuevo) | Pruebas de extremo a extremo sobre `make_db()` con la composición de producción: criterio 1 (éxito → 2 filas), 6 (mensaje de sitio en la etiqueta, `result()` ≠ Accepted; `QApplication` en fixture de módulo), 7 (logout → REVOKED con `session_id`), 10 (sin contraseña, hashes ni token de recuperación en ninguna fila; incluye REQUESTED/COMPLETED), 13 (aprovisionamiento real deja STARTED+PROVISIONED; con falla forzada y rollback, ninguna). | Suites nuevas verdes. |
| 13 | `tests/architecture/test_security_does_not_import_bootstrap.py` (nuevo) | Criterio 14: ningún `.py` bajo `backend/security/` importa `backend.bootstrap` (AST, anclado a `APP_ROOT`). | Pasa. |
| 14 | Copia de la BD real en scratchpad (script en scratchpad, no en el repo) | Criterio 16: copiar la base real a `%TEMP%`; `PRAGMA table_info(audit_logs)` (12 columnas); login exitoso, contraseña incorrecta y denegación por sitio con caso de uso y sink reales; consultar filas. Salida guardada para `test-report.md` (la redacta `/sdlc-test`). | Salida con las filas esperadas. |
| 15 | `migrations/MIGRATION_LOG.md`, `docs/sdlc/BACKLOG.md`, `items/SDLC-UI-016/intent.md` | Entrada en el log (sin migración: cambio de comportamiento de auditoría). Nota en UI-016: «al construir `ApplicationContextService`, pasar `build_security_audit_sink(conn)`». Nota en `items/SDLC-ARQ-AUD-003/intent.md`: rechazo móvil por permiso sin auditar. Etapa → `en-test`. | Línea base completa re-ejecutada; mismo conjunto de fallos previos, ninguno nuevo. |

## Archivos que NO se tocan
- Shims de WhatsApp (`services/whatsapp_service.py`, `integrations/whatsapp_service.py`, `whatsapp_service/webhook/whatsapp.py`) y de finanzas: ajenos al ítem.
- `frontend/desktop/app.py`: hereda el respaldo de terminal (ver Nota).
- `frontend/desktop/auth/authentication_coordinator.py`: conserva su `except SiteAccessDeniedError` como defensa en profundidad ante la carrera del ancla (spec, «Carrera»).
- Los 5 llamadores de escritorio de `build_authorizer_credentials_verifier` (Caja, Cárnico, Transferencias, Fidelidad, POS): reciben el sink por el valor por defecto de la fábrica.
- `SqliteAuditLogRepository` y el esquema de `audit_logs`: se reutilizan tal cual.
- `authentication_attempts` (esquema y repositorio): `site_access_denied` es un valor nuevo en una columna de texto libre.
- Rechazo móvil por `LOGISTICA.embarque.ver` (`backend/api/mobile_credentials.py:42`): fuera de alcance, va a SDLC-ARQ-AUD-003.
- Unificación de tablas de auditoría: SDLC-ARQ-AUD-002.

## Migraciones
Ninguna. `audit_logs` ya tiene todas las columnas (`migrations/m000_base_schema.py:2386-2399`). La verificación sobre copia de la base real es el paso 14. Reversa: revertir los commits; las filas `SEGURIDAD` escritas quedan como historial válido.

## Criterio de terminado
| Criterio del spec | Prueba |
|---|---|
| 1 Login exitoso → SUCCEEDED + SESSION_CREATED | paso 12, `test_security_audit_production_wiring.py` |
| 2 Contraseña incorrecta / usuario inexistente | paso 8 |
| 3 ACCOUNT_LOCKED + intento bloqueado sin alargar | paso 8 |
| 4 Denegación por sitio | paso 8 |
| 5 Cinco denegaciones no bloquean | pasos 5 y 8 |
| 6 LoginWindow muestra el mensaje | paso 12, `test_login_window_site_denied.py` |
| 7 Logout → REVOKED | paso 12 |
| 8 Autorizador / móvil con `purpose` | paso 9 |
| 9 Cambio de sucursal | paso 10 |
| 10 Sin secretos | paso 12 |
| 11 Lista negra de claves | paso 6 |
| 12 Evento desconocido persistido | paso 6 |
| 13 Aprovisionamiento y rollback | paso 12 |
| 14 Arquitectura + `build()` usa el método | pasos 4 y 13 |
| 15 Regresión + `recent()` | pasos 6 y 15 |
| 16 Copia de la base real | paso 14 |

## Notas de Build (2026-10-29/30)

### Desviación 1 — APROBADA (2026-10-30, Alfred, opción b): `branch_id` en los eventos de sesión
El Hueco 1 (aprobado) agregó `branch_id` de la sesión a `USER_SESSION_*`. Al construirlo se vio que `UserSession.branch_id` es la **sucursal propia del usuario** (`authenticate_user_use_case.py`, `create_session(branch_id=credentials.branch_id)`), no el sitio de la estación que opera el contexto. Como el sink toma `branch_id` del payload antes que el ancla, las filas `USER_SESSION_*` quedan con la sucursal propia en `sucursal_id`, mientras que las `USER_AUTHENTICATION_*` del mismo login quedan con el ancla. Eso contradice el borde del spec («`sucursal_id` es el sitio anclado a la estación en el momento del evento»). Sólo el payload nuevo lee `UserSession.branch_id` (grep sobre `backend/` y `frontend/`), así que no hay otro efecto.
- (a) Dejarlo como está.
- (b) **Recomendado:** emitir la clave como `session_branch_id`, de modo que `sucursal_id` = ancla y la sucursal propia sigue en `detalles`. Cambio de 1 línea en `session_manager.py` + ajuste de `test_session_events_carry_workstation_and_branch`.
- Los tests pasaban con (a) porque en sus escenarios la sucursal propia coincidía con el ancla.
- **Aplicada:** `session_manager.py` emite `session_branch_id`; prueba nueva `test_session_rows_record_the_station_site_not_the_users_home_branch` (dueño con sucursal propia Centro en estación anclada a Chihuahua: ambas filas con `sucursal_id`=Chihuahua).

### Cambios menores fuera del texto del plan (no alteran contratos)
- Paso 6 adelanta la constante `APPLICATION_CONTEXT_SWITCH_DENIED` (archivo del paso 10) porque el sink la clasifica como fallo.
- `SiteDenial.display_name` (`site_name or site_id`), para que el builder y el caso de uso muestren lo mismo que antes.
- `tests/integration/_site_scenario.py`: escenario Centro/Chihuahua compartido por R1, el caso de uso y la prueba de UI (evita triplicar la fixture).
- `mobile_credentials.py` pasa además `workstation_id=device_id`: la terminal del login móvil queda en el evento y en `authentication_attempts.workstation_id` (antes `""`). El bloqueo es por usuario, no cambia.

### Línea base re-ejecutada al cerrar el Build (2026-10-30, paso 15)
| Comando | Resultado |
|---|---|
| segmento de la línea base + `tests/integration/logistics/test_mobile_api_host_32cfbf.py` | **712 passed**, 0 failed (13 min 41 s) |
| `tests/ui/test_authentication_coordinator.py` · `test_login_window.py` · `test_login_window_site_denied.py` · `test_initial_setup_wizard.py` | 12 · 7 · 1 · 17 passed |
| `python -m pytest tests/architecture -q` | **22 failed, 881 passed**, 1 skipped, 2 xfailed (28 min 35 s): los mismos 22 nombres de la línea base, ninguno nuevo; +2 por la guarda nueva |
| tras la Desviación 1: `test_session_manager.py` + `test_authenticate_user_use_case.py` + `test_security_audit_production_wiring.py` + `test_security_audit_sink.py` | 50 passed |

### Evidencia de Build — copia de la base real (paso 14, criterio 16)
Script y salida en el scratchpad de la sesión (`step14_real_copy.py`, `step14_output.txt`). Origen `data/spj_pos_database.db` (13 762 560 bytes) abierto en modo sólo lectura y copiado con la API de respaldo de SQLite; la conexión de la copia es la de la app (`_new_connection`, `isolation_level=None`). Usuarios de prueba `aud001_*` creados **sólo en la copia** (las claves reales no se conocen).
- `PRAGMA table_info(audit_logs)`: **13** columnas (las 12 del spec + `operation_id`, de una migración posterior; el sink no la usa).
- Ancla: «Corregidora». Login exitoso → `USER_AUTHENTICATION_SUCCEEDED` + `USER_SESSION_CREATED` (`exito`, `ws=AUD001-PC`, `sucursal_id`=ancla). Contraseña incorrecta → `USER_AUTHENTICATION_FAILED motivo=invalid_password`, `usuario=aud001_dueno`. Cajero con rol en otra sucursal → `SiteAccessDeniedError` («Corregidora»), `authentication_attempts` = `(0, site_access_denied)` sin SUCCEEDED, `USER_AUTHENTICATION_FAILED motivo=site_access_denied`.
- Contraseña o hash en las filas: **no**.
- Hallazgo: la copia ya traía 3 filas `SEGURIDAD` previas (estación `LAPTOP-9AUM7IBI`: un `invalid_password` y un login exitoso con su `USER_SESSION_CREATED`), escritas antes de este script — alguien abrió la app con el código de esta rama tras el paso 11. No verificado quién.
