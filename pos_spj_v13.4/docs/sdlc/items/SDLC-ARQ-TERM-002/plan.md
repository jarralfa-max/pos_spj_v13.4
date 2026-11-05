# SDLC-ARQ-TERM-002 — Plan de implementación

- **Spec:** `items/SDLC-ARQ-TERM-002/spec.md` (aprobado por autopiloto el 2026-11-02)
- **Rama:** `sdlc/sdlc-arq-term-002` desde `claude/erp-financial-bounded-context-uqxz6b` @ `1c4786a7`
- **Estado:** aprobado por autopiloto (2026-11-02) — pendiente de revisión humana en el PR

## Línea base

Ejecutada sobre una copia exacta de `1c4786a7` (`git archive` a `D:\spj_tmp\term-002\base`) para que
ningún cambio del ítem la contamine. Entorno: Windows 11, Python 3.13, `QT_QPA_PLATFORM=offscreen`,
`-p no:cacheprovider`, temporales en `D:\spj_tmp\term-002`.

| Segmento | Comando (desde `pos_spj_v13.4/`) | Resultado |
|---|---|---|
| Área tocada | `python -m pytest tests/unit/test_empresa_page_installation_branch.py tests/integration/configuracion tests/integration/bootstrap tests/unit/bootstrap tests/unit/configuracion tests/integration/shell/test_desktop_shell_composition_end_to_end.py tests/unit/test_configuracion_ui_workspace.py -q` | en curso (se anota al terminar) |
| Seguridad | `python -m pytest tests/unit/security tests/integration/security -q` | en curso (se anota al terminar) |
| Arquitectura | `python -m pytest tests/architecture -q` | en curso (se anota al terminar) |

Nota: la máquina está muy cargada (otras sesiones corren suites en paralelo; una corrida del área tardó 2 h). El plan se confirma antes de que termine la línea base para que sobreviva a una interrupción; los números reales se anotan en un commit posterior y `test-report.md` los compara.

Referencia: `docs/sdlc/baseline/2026-10-28.md` (22 fallas preexistentes en arquitectura, 4 en unit, colección
de integration rota por `tests/integration/test_sqlite_sales_repository_uuid.py`).

## Pasos
| # | Archivo(s) | Cambio | Verificación del paso |
|---|---|---|---|
| 1 | `tests/integration/configuracion/test_installation_branch_reanchor.py` | Prueba de regresión: fija lo que se conserva (ancla sembrada, set/get, rechazo de sucursal inexistente/inactiva, el login opera el sitio anclado) y reproduce los 3 defectos tal como están hoy (caso de uso sin permiso, sin auditoría, fallback a la sucursal propia). | `pytest tests/integration/configuracion/test_installation_branch_reanchor.py` → 7 pasan sobre el código base |
| 2 | `backend/application/configuracion/permissions.py`, `migrations/standalone/357_seed_installation_reanchor_permission.py`, `migrations/engine.py`, `migrations/MIGRATION_LOG.md`, `tests/integration/configuracion/_reanchor_support.py`, `tests/integration/configuracion/test_reanchor_permission_seed.py` | Código `CONFIGURACION.estacion.reanclar` (el catálogo lo deriva solo); migración 357 que lo siembra a `system_owner` y `admin`, registrada y documentada. | `pytest …/test_reanchor_permission_seed.py` → 4 pasan (catálogo, sólo roles de acceso total, idempotencia, registrada en el motor) |
| 3 | `backend/domain/settings/exceptions.py`, `backend/infrastructure/db/repositories/settings/installation_branch_repository.py`, `…/installation_branch_unit_of_work.py`, `tests/integration/configuracion/test_installation_branch_guards.py` | `InstallationBranchChangeRejectedError`; consultas `central_enrollment_active`, `open_cash_shifts_outside`, `pending_sync_count`; `InstallationBranchUnitOfWork` (ancla + auditoría). | `pytest …/test_installation_branch_guards.py` → pasan (turnos terminales/no terminales, sobres por estado, hecho sin sobre, vinculación central, reversa conjunta) |
| 4 | `backend/application/use_cases/set_installation_branch_use_case.py`, `backend/application/commands/settings_commands.py`, `backend/application/configuracion/settings_services.py`, `frontend/desktop/modules/configuracion/configuracion_routes.py`, `frontend/desktop/modules/configuracion/configuracion_presenter.py`, pruebas: `test_installation_branch_reanchor_use_case.py` (nueva), `test_installation_branch_reanchor.py` (se retiran los 2 defectos del caso de uso), `test_settings_services.py` (escribe vía repositorio), `tests/unit/test_empresa_page_installation_branch.py` (+1) | Caso de uso con permiso en backend, guardas dentro de la UoW (ancla primero = candado), auditoría aplicada/rechazada, idempotencia; se retira `CompanyProfileService.set_installation_branch`; cableado con política de sesión y UoW; el presentador sólo traduce. | `pytest` de los cuatro archivos → pasan |
| 5 | `backend/bootstrap/application_context_builder.py`, `backend/bootstrap/application_context_errors.py`, `test_station_without_anchor.py` (nueva), `test_installation_branch_reanchor.py` (se retira el defecto del fallback) | Sin ancla: `StationNotAnchoredError` o sesión de reparación (`branch_id=''`, `site_capabilities=frozenset()`) para quien tiene el permiso. | `pytest …/test_station_without_anchor.py tests/integration/bootstrap tests/integration/security/test_contextual_permissions.py` → pasan |
| 6 | `docs/sdlc/items/SDLC-ARQ-TERM-002/test-report.md` | Segmentos y comparación con la línea base. | ver reporte |

## Archivos que NO se tocan
- `docs/sdlc/BACKLOG.md` y artefactos de otros ítems (restricción del autopiloto).
- `frontend/desktop/modules/configuracion/pages/empresa_page.py`: propagar el cambio a la sesión viva es SDLC-SET-001.
- `backend/security/provisioning/provision_installation_use_case.py`: el flujo de provisión ya escribe el ancla (E7).
- `migrations/standalone/354_device_enrollment.py` y `backend/application/sync/device_provisioning.py`: sólo se leen; si 354 entra al motor es SDLC-SYNC-001 / TERM-004.
- `SqliteOrgUnitRepository.open_cash_shifts`: comportamiento ajeno (cierre de unidades).
- Shims de WhatsApp y `core/` (CLAUDE.md §8-9): no se tocan.
- `tests/test_installation_branch_resolution.py`: importa módulos `core.*` ya borrados; está fuera de las suites que corren (lo señala el intent) y no se rescata aquí.

## Migraciones
`357_seed_installation_reanchor_permission.py` (sólo datos, idempotente). Se prueba sobre `make_db()` +
350 + 357 en memoria (`_reanchor_support.build_template`). Reversa: borrar las filas
`CONFIGURACION`/`estacion.reanclar` de `rol_permisos` y la versión 357 de `schema_migrations`.

## Criterio de terminado
| Criterio (spec) | Prueba |
|---|---|
| 1 | `test_installation_branch_reanchor_use_case.py::test_editing_the_company_is_not_enough`, `tests/unit/test_empresa_page_installation_branch.py::…::test_editing_the_company_no_longer_allows_re_anchoring` |
| 2 | `…_use_case.py::test_without_a_wired_policy_it_fails_closed` |
| 3 | `…_use_case.py::test_an_open_shift_blocks_the_change`, `::test_closed_or_cancelled_shifts_do_not_block`; `…_guards.py` turnos |
| 4 | `…_use_case.py::test_unsynced_envelopes_block_the_change`, `::test_an_unstaged_fact_blocks_the_change`, `::test_only_synced_or_dead_envelopes_let_it_through` |
| 5 | `…_use_case.py::test_an_enrolled_station_is_reassigned_by_the_central_registry`, `::test_without_a_central_registry_the_local_permission_is_enough` |
| 6 | `…_use_case.py::test_success_writes_the_anchor_and_its_audit_row`, `::test_a_failed_audit_rolls_the_anchor_back` |
| 7 | `…_use_case.py::test_re_anchoring_to_the_current_branch_is_a_no_op` |
| 8 | `test_station_without_anchor.py` (6 pruebas) |
| 9 | `test_reanchor_permission_seed.py` (4 pruebas) |
| 10 | `test_installation_branch_reanchor.py::TestSeConserva`, `test_settings_services.py` (sucursal de instalación), `test_empresa_page_installation_branch.py` |
