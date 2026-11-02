# SDLC-UI-001 — Plan de implementación

- **Spec:** `items/SDLC-UI-001/spec.md` (aprobado el 2026-10-30 por Alfred; D1–D5 = opciones recomendadas)
- **Rama:** `sdlc/sdlc-ui-001` desde `sdlc/sdlc-arq-aud-001` @ `1b288d04` (decisión del responsable 2026-10-30: la rama base del README, `claude/erp-financial-bounded-context-uqxz6b`, va 29 commits detrás y no contiene ni el plan UI `30d3661f` ni el spec `f808e8eb`; el PR queda apilado detrás del de SDLC-ARQ-AUD-001)
- **Estado:** aprobado (2026-10-31, Alfred; sin observaciones: se reutiliza `tests/architecture/test_ci_workflow.py` y el paso 9 commitea `SDLC-UI-002/intent.md` con su aprobación)

Rutas relativas a `pos_spj_v13.4/` salvo `../.github/…`. Nota de ejecución: pytest toma como rootdir la raíz del repo (por `../pyproject.toml`), así que los nodeids llevan prefijo `pos_spj_v13.4/` (un `--deselect tests/ui/…` no casa nada).

## Línea base
Ejecutada el 2026-10-30 en `sdlc/sdlc-ui-001` antes de cambiar nada (Windows 11, Python 3.13.12, PyQt5 5.15.11, pytest 9.1.1, `QT_QPA_PLATFORM=offscreen`).

| Comando | Resultado real |
|---|---|
| `python -m pytest tests/ui/test_operations_standard_dialogs.py -q` | **código 127**, 9 bytes de salida (`........F`): 8 pasan, `test_payment_enter_adds_local_line_and_cancel_never_starts_checkout` falla (SDLC-UI-002) y el proceso muere en `test_payment_retry_keeps_recorded_lines_and_accepts_once` |
| `python -m pytest tests/ui -q` | **código 127 sin resumen** (medido dos veces en `/sdlc-plan` 2026-10-29 y en Design 2026-10-30; el código no cambió desde entonces) |
| `python -m pytest tests/ui -q -p ui001_hook` (plugin de sonda fuera del repo que sólo instala `sys.excepthook`) | `107 failed, 1377 passed in 1052.50s` — referencia de lo que debe dar la suite tras el paso 2 |
| `python -m pytest tests/architecture -q` | ❌ `22 failed, 881 passed, 1 skipped, 2 xfailed in 4850.91s (1:20:50)` — mismas 22 que la línea base 2026-10-28 (en 18 archivos: `test_design_system_guardrails.py` ×2, `test_refactor_orchestrator.py` ×4, …). Nodeids en `baseline/architecture-failed.txt` |
| `python -m pytest tests/unit -q` (se corre porque D1 cambia `tests/conftest.py`, que aplica a todas las suites) | ❌ `5 failed, 6183 passed in 352.80s`: `sales_pos/test_live_scale.py` ×1 (fecha), `test_feature_flags_page.py` ×2, `test_pos_checkout_dialogs.py::test_reintentar_el_cobro_no_duplica_pagos` (`AttributeError: module 'PyQt5.QtWidgets' has no attribute 'MessageDialog'` en `:82` — parche desactualizado tras el codemod de MessageDialog, **no** es el abort de este ítem), `test_transfers_ui_workspace.py` ×1. Nodeids en `baseline/unit-failed.txt` |

Las 107 fallas de la corrida con sonda quedan en `baseline/ui-with-hook-failed.txt` (referencia del paso 8).

## Pasos
| # | Archivo(s) | Cambio | Verificación del paso |
|---|---|---|---|
| 1 | `tests/ui/_guard_probes/probe_slot_exception.py`, `tests/ui/_guard_probes/probe_unintercepted_modal.py` (nuevos; nombres sin `test_` para que la corrida normal no los colecte), `tests/ui/test_qt_test_guards.py` (nuevo) | **Regresión que fija el comportamiento actual.** Sondas: (a) una prueba conecta `clicked` de un `QPushButton` a un slot que lanza `RuntimeError("sonda-slot")` y hace `click()`; una segunda prueba pasa. (b) una prueba crea un `QDialog` con título «Sonda modal» y llama `exec_()` sin parche. La meta-prueba corre cada sonda con `subprocess.run([sys.executable, "-m", "pytest", <sonda>, "-q", "-p", "no:cacheprovider"], cwd=pos_spj_v13.4, env QT_QPA_PLATFORM=offscreen, timeout=60)` — pytest colecta un archivo pasado por argumento aunque no case `test_*.py`, y las sondas viven bajo `tests/ui/` para que apliquen los conftest reales | Hoy **rojo y documentado**: la sonda (a) termina con código ≠ 1 sin resumen; la (b) agota el `timeout`. Commit `test(ui): sondas que fijan el abort por excepción en slot y el cuelgue por modal [SDLC-UI-001]` |
| 2 | `tests/qt_guards.py` (nuevo, funciones sin fixtures), `tests/conftest.py` | **D1.** `install_slot_exception_hook()` instala un `sys.excepthook` que acumula tracebacks en una lista del módulo (idempotente); `pytest_configure` existente (`tests/conftest.py:301`) lo llama. Fixture autouse `_qt_slot_exceptions_fail_the_test` limpia la lista al inicio y hace `pytest.fail("Excepción en un slot de Qt:\n…")` al final si hubo alguna | Sonda (a) verde: código 1, `1 failed, 1 passed`, `sonda-slot` en la salida. `test_payment_retry…` sola → código 1 con `AttributeError … 'data'` (falla normal, ya no 127). Commit `fix(tests): una excepción en un slot de Qt falla la prueba en vez de abortar pytest [SDLC-UI-001]` |
| 3 | `tests/qt_guards.py`, `tests/ui/conftest.py` | **D2.** Fixture autouse `_unintercepted_dialogs_fail_instead_of_hanging` en `tests/ui/conftest.py`: `monkeypatch.setattr(QDialog, "exec_", …)` que registra el título, hace `reject()` y devuelve 0; al final falla si se registró alguno. No toca `QMenu.exec_`. La guardia de `MessageDialog` de `tests/conftest.py:316-336` queda igual (más específica en el MRO) | Sonda (b) verde: termina en < 30 s con `1 failed` y «Sonda modal» en el mensaje. Sin regresión: `tests/ui/test_message_dialog.py`, `test_standard_dialog_prompts.py`, `test_authentication_coordinator.py`, `tests/ui/shell/` pasan como antes. Commit `fix(tests): un QDialog modal sin interceptar falla la prueba en vez de colgar [SDLC-UI-001]` |
| 4 | `tests/ui/test_operations_standard_dialogs.py` | Doble alineado al contrato real: `_result()` devuelve `SaleResult` (`backend/application/sales/result.py:52`); `record_payment` devuelve `data={"sale": …}` con un pago de id `019f327a-1694-7000-8000-000000000004`; `Presenter.void_payment` registra la llamada. La prueba intercepta `CancelSaleDialog.exec_` (devuelve 0) y afirma: secuencia `begin, payment, checkout, checkout`; `void_payment` no llamado; `len(_lines) == 1` tras cancelar la anulación; una sola emisión de `accepted`; `presenter.calls[1][1]` igual que hoy | La prueba sola → código 0. El archivo completo → sólo `test_payment_enter…` falla (SDLC-UI-002). Commit `fix(tests): el doble de cobro usa SaleResult y fija la anulación cancelada [SDLC-UI-001]` |
| 5 | `tests/conftest.py`; archivos de D3 (`pytestmark = pytest.mark.ui_ci`): todo `tests/ui/shell/` (vía `pytestmark` por archivo), `test_message_dialog.py`, `test_standard_dialog_prompts.py`, `test_standard_dialog_footer.py`, `test_numeric_keypad_standard_dialog.py`, `test_account_recovery_dialog.py`, `test_finance_hr_standard_dialogs.py`, `test_finance_remaining_standard_dialogs.py`, `test_products_standard_dialog_adoption.py`, `test_authentication_coordinator.py`, `test_login_window.py`, `test_login_window_site_denied.py`, `test_login_password_controls.py`, `test_specialized_inputs.py`, `test_entity_search_keyboard.py`, `test_formatters.py`, `test_design_system_registry.py`, `test_purchasing_visual_closure.py`, `test_qt_test_guards.py`; en `test_operations_standard_dialogs.py` la marca va por función en las 9 que no son `test_payment_enter…` | Registrar `ui_ci` en `pytest_configure` (junto a `unwired_fails_closed`) | `python -m pytest tests/ui -m ui_ci -q` → código 0; se anotan pruebas seleccionadas y duración. Si un archivo de la lista falla hoy, se saca de `ui_ci` y se anota aquí como desviación (no se relaja la prueba). Commit `test(ui): marca ui_ci para el subconjunto de CI [SDLC-UI-001]` |
| 6 | `tests/architecture/test_ci_workflow.py` (existente — **ajuste respecto del spec**, que proponía un archivo nuevo `test_ci_workflow_scripts.py`; se reutiliza el que ya protege el workflow) | Reemplazar `test_ci_keeps_sales_ui_and_api_domain_jobs` (`:68-74`, hoy **fija el defecto** como contrato) por: (a) `test_ci_run_steps_only_call_existing_local_scripts` — todo token `./…` o `scripts/…` de un `run:` existe (relativo a la raíz o al `cd` del paso); se ejercita también con un YAML de ejemplo que reintroduce `./scripts/ci/run_domain_tests.sh` y debe dar falla; (b) `test_ci_runs_the_ui_ci_subset` — algún job corre `python -m pytest tests/ui -m ui_ci` y la marca selecciona > 0 pruebas (`--collect-only -m ui_ci` en subproceso) | Antes del paso 7: (a) **rojo** contra el workflow actual, (b) rojo. Commit `test(ci): el workflow no puede llamar scripts inexistentes y debe correr ui_ci [SDLC-UI-001]` |
| 7 | `../.github/workflows/ci-segmented.yml` | **D5.** Quitar los jobs `ventas`, `ui`, `api` (`:106-167`). Agregar job `ui-subset` (misma instalación de dependencias que `procurement-logistics-quality`, `QT_QPA_PLATFORM: offscreen`, `PYTHONUNBUFFERED: "1"`) con paso `cd pos_spj_v13.4 && python -m pytest tests/ui -m ui_ci -q`. El paso de `test_purchasing_visual_closure.py` y su artefacto no cambian | `python -m pytest tests/architecture/test_ci_workflow.py -q` verde. El job real se valida en el CI del PR (etapa Test/Deploy). Commit `ci: retirar jobs ventas/ui/api sin script y correr ui_ci en job propio [SDLC-UI-001]` |
| 8 | — | Corridas completas de verificación | (i) `python -m pytest tests/ui -q` **sin plugins** llega al resumen; las fallas por nodeid = las 96 de SDLC-UI-002 + las 10 de D4, ni una más (`test_payment_retry…` ya no está). (ii) `tests/architecture` sin fallas nuevas por nodeid contra la línea base. (iii) `tests/unit` sin fallas nuevas por nodeid contra la línea base. Resultados en este plan / test-report |
| 9 | `docs/sdlc/BACKLOG.md`, `docs/sdlc/items/SDLC-UI-002/intent.md`, `migrations/MIGRATION_LOG.md` | **D4**: la fila de SDLC-UI-002 pasa de «96 fallas» a «106 fallas» y su intent gana una sección «Ampliación (SDLC-UI-001 D4)» con las 10 fallas y su evidencia (`bank_reconciliation_page.py:189`, `components/dialogs.py:39`, `AccountsReceivablePage._show_crm_summary`, `test_page_stack.py:45`). Entrada en `MIGRATION_LOG.md` (retiro de jobs de CI, guardias de pruebas Qt). Etapa → `en-test` | Diff de `BACKLOG.md` contra `HEAD` revisado (sólo filas de UI-001/UI-002). Commit `docs(sdlc): UI-002 ampliado, log y etapa en-test [SDLC-UI-001]` |

## Resultados del paso 8 (2026-10-31)
Corridas completas sobre `807b8468`, `QT_QPA_PLATFORM=offscreen`, `-p no:cacheprovider`. Comparación por nodeid contra `baseline/` (parámetros de fecha normalizados).

| Suite | Resultado | Contra la línea base |
|---|---|---|
| `tests/ui` (sin `-m`, sin plugins de diagnóstico) | llega al resumen: 107 failed, 1379 passed en 752 s (1486 = 1484 + las 2 meta-pruebas de guardias) | Sale `test_payment_retry_keeps_recorded_lines_and_accepts_once`. Entra 1: `test_standard_window_geometry.py::test_screen_change_rebinds_available_area_and_disconnects_previous` (ver desviación). Las otras 106 = 96 de SDLC-UI-002 + 10 de D4 |
| `tests/unit` | 4 failed, 6184 passed en 355 s | Ninguna nueva. Sale `sales_pos/test_live_scale.py::test_capture_rejects_future_naive_or_unstable_readings` (depende de la fecha; no la toca este ítem) |
| `tests/architecture` | 22 failed, 883 passed, 1 skipped, 2 xfailed en 2819 s | Mismas 22 por nodeid. +2 aprobadas: `test_ci_workflow.py` gana 3 pruebas y pierde 1 |

**Desviación del criterio 4 («96 + 10, ni una más»): 1 falla intermitente previa.** `test_screen_change_rebinds_available_area_and_disconnects_previous` (`tests/ui/test_standard_window_geometry.py:131`, la ventana queda 2 px fuera del área) pasó en la línea base y falló en esta corrida. Aislada: falla 5 de 10 veces con las guardias y 7 de 12 con las guardias neutralizadas por un plugin de diagnóstico del scratchpad (`qt_guards.guard_phase` sustituido por un passthrough y `sys.excepthook` restaurado). La intermitencia no la introduce este ítem. No se corrige aquí (regla 5 de Build): queda como **SDLC-UI-031** (`intent-borrador`). Pendiente de tu aprobación: aceptar el criterio 4 con esta salvedad.

## Archivos que NO se tocan
- `frontend/desktop/modules/sales_pos/dialogs/payment_dialog.py` y todo `frontend/`, `backend/`: el defecto está en la prueba, no en producción (spec, diagnóstico 3).
- Las 96 + 10 fallas restantes de `tests/ui` (SDLC-UI-002), incluida `test_payment_enter…` en el mismo archivo.
- `tests/architecture/design_system_debt_baseline.json` (no se amplía; política del archivo y SDLC-UI-003).
- Shims de `CLAUDE.md` (finance, los 3 de WhatsApp) y `core/events/event_bus.py`: fuera de alcance.
- `test_purchasing_visual_closure.py`, su paso de CI y su artefacto; jobs `procurement-logistics-quality` y `central-postgres` (salvo nada).
- `../.github/workflows/windows-release.yml`.
- `docs/sdlc/items/SDLC-UI-003/intent.md`: tiene tu aprobación sin commitear; no es de este ítem.

**Nota sobre `SDLC-UI-002/intent.md`:** hoy tiene tu aprobación sin commitear (estado y respuesta «14 secciones»). El paso 9 le agrega la sección de D4 y lo commitea, lo que incluye esas dos líneas tuyas. Si prefieres que no, el paso 9 deja la ampliación sólo en `BACKLOG.md`.

## Migraciones
No hay. No se toca ninguna base.

## Criterio de terminado
| Criterio del spec | Prueba / evidencia |
|---|---|
| 1. Excepción en slot falla la prueba sin derribar la corrida | `tests/ui/test_qt_test_guards.py` (sonda a) |
| 2. Modal sin interceptar falla en vez de colgar | `tests/ui/test_qt_test_guards.py` (sonda b) |
| 3. Prueba de cobro pasa sola con las aserciones nuevas | `test_operations_standard_dialogs.py::test_payment_retry_keeps_recorded_lines_and_accepts_once` |
| 4. `tests/ui` llega al resumen con exactamente 96 + 10 fallas | paso 8 (i), comparación por nodeid |
| 5. `-m ui_ci` verde en Windows y en CI | paso 5 (Windows); job `ui-subset` del PR (Test) |
| 6. CI sin scripts fantasma; reintroducirlo falla | `tests/architecture/test_ci_workflow.py` (paso 6) |
| 7. `tests/architecture` sin fallas nuevas; baseline JSON intacto | paso 8 (ii); `git diff` no toca el JSON |
| 8. Sin cambios de producción | `git diff --stat sdlc/sdlc-arq-aud-001...sdlc/sdlc-ui-001` sólo `tests/`, `../.github/workflows/ci-segmented.yml`, `docs/sdlc/`, `migrations/MIGRATION_LOG.md` |
