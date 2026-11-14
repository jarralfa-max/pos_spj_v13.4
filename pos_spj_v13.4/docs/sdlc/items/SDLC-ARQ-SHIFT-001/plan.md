# SDLC-ARQ-SHIFT-001 — Plan de implementación

- **Spec:** `items/SDLC-ARQ-SHIFT-001/spec.md` (aprobado por autopiloto el 2026-11-02)
- **Rama:** `sdlc/sdlc-arq-shift-001` desde `claude/erp-financial-bounded-context-uqxz6b` @ `1c4786a7`
- **Estado:** aprobado por autopiloto (2026-11-02) — pendiente de revisión humana en el PR

## Línea base
Ejecutada en `1c4786a7` (Windows 11, Python 3.13, `QT_QPA_PLATFORM=offscreen`, `-p no:cacheprovider`, temporales en `D:\spj_tmp\shift-001`), desde `pos_spj_v13.4/`:

| Segmento | Comando | Resultado |
|---|---|---|
| Arquitectura de Caja/POS | `python -m pytest tests/architecture/test_cash_*.py tests/architecture/test_sales_pos_ui_has_no_sql.py tests/architecture/test_sales_domain_contract.py -q` | **108 passed** |
| Caja integración + unit + e2e | `python -m pytest tests/integration/cash_register tests/unit/cash_register tests/e2e/test_cash_sales_integration.py tests/unit/test_cash_register_shell_registration.py -q` | **265 passed**, 15 subtests passed |
| Ventas/POS, Organización, Actualizaciones, Finanzas | `python -m pytest tests/integration/sales tests/integration/test_sales_checkout_settles_everything.py tests/integration/test_sales_pos_checkout_end_to_end.py tests/integration/test_sales_pos_reverse_reconstruction.py tests/unit/sales_pos tests/unit/test_sales_use_cases.py tests/unit/test_sales_suspension.py tests/unit/test_pos_checkout_dialogs.py tests/integration/organization tests/unit/organization tests/integration/software_distribution tests/unit/software_distribution tests/integration/finance tests/unit/finance -q` | **3 failed, 732 passed** (17:41). Preexistentes: `test_sales_checkout_settles_everything.py::test_con_autorizacion_y_motivo_se_cobra_y_queda_negativo_y_auditado` y `::test_la_autorizacion_sin_existencia_se_valida[sin_permiso]` (`OperationalError: no such column: sucursal_id` en `backend/infrastructure/db/repositories/security/base.py:18`, fixtures sin `usuarios.sucursal_id`, mismo grupo que SDLC-CORE-011); `tests/unit/test_pos_checkout_dialogs.py::test_reintentar_el_cobro_no_duplica_pagos` (`PyQt5.QtWidgets` sin `MessageDialog`, ya en `docs/sdlc/baseline/2026-10-28.md` → SDLC-CORE-010) |
| Arquitectura completa | `python -m pytest tests/architecture -q` (sobre una copia `git archive 1c4786a7` en el scratchpad, para no mezclarla con las ediciones) | ver `test-report.md` (corrida de ~20 min en segundo plano) |

## Pasos
| # | Archivo(s) | Cambio | Verificación del paso |
|---|---|---|---|
| 1 | `tests/integration/cash_register/test_active_shift_coherence.py` (nuevo) | Prueba de regresión: fija lo que ya coincide (OPEN, SUSPENDED/CLOSING visibles en Caja y contados en Finanzas, apertura bloqueada, cobro sin ledger, sin turno, recuentos) y reproduce con `expectedFailure` las divergencias: POS no dice "suspendido"/"cierre" ni identifica el turno, caché `active_cash_shift_id` en el `composition_root`, Organización cuenta `CANCELLED` | `pytest tests/integration/cash_register/test_active_shift_coherence.py` → **6 passed, 4 xfailed** (verificado; cada xfail falla por su aserción, no por el arnés) |
| 2 | `backend/domain/cash_register/policies/workflow_policies.py`, `backend/domain/cash_register/exceptions.py`, `tests/unit/cash_register/test_active_shift_policy.py` (nuevo) | `CLOSING_STATUSES`, `active_status_values()`, `closing_status_values()`, `CashShiftOperability` + `operability()`; `CashShiftNotOpenError` / `CashShiftSuspendedError` / `CashShiftClosingError` (heredan de `CashInvalidStateError`) | prueba unitaria nueva + `tests/unit/cash_register` |
| 3 | `backend/infrastructure/db/repositories/cash_register/repositories.py`, `backend/application/cash_register/active_shift_resolver.py` (nuevo), `sales_integration.py`, `refund_integration.py`, `shift_use_cases.py`, `tests/integration/cash_register/test_active_shift_resolver.py` (nuevo) | Repositorio: `find_active`, `active_register_ids`, `count_active`, `count_closing`; se borran los tres `find_*` viejos. Resolvedor de aplicación. Cobro y reembolso → `require_operable`; apertura → `for_cashier`/`for_resource` (mismos mensajes) | prueba nueva + `tests/integration/cash_register` + `tests/e2e/test_cash_sales_integration.py` |
| 4 | `backend/infrastructure/integrations/sales_cash_effects_client.py`, `frontend/desktop/modules/sales_pos/composition.py`, `backend/application/sales/use_cases/checkout_use_cases.py`, `backend/application/sales/use_cases/return_use_cases.py` | `SalesCashEffectsClient.open_shift_problem(...)` delega en el resolvedor; las tres copias del POS lo usan | quitar `expectedFailure` de las dos pruebas del POS → pasan; segmento Ventas/POS |
| 5 | `backend/infrastructure/desktop/cash_operational_context.py`, `backend/infrastructure/desktop/cash_register_factory.py`, `frontend/desktop/modules/cash_register/shell_registration.py` (docstring), `tests/unit/test_cash_register_shell_registration.py`, `tests/architecture/test_cash_operational_context_resolver.py`, `tests/integration/cash_register/test_cash_refund_factory_wiring.py`, `test_cash_register_factory_alerts.py` | Contexto de Caja delega en el resolvedor (turno y cajas ocupadas); se borra la caché `active_cash_shift_id` (lectura y escrituras). La guardia existente del contexto pasa a exigir el resolvedor en vez de su SQL propio; los dobles de prueba dejan de sembrar la caché | quitar `expectedFailure` de la prueba de caché → pasa; segmento Caja |
| 6 | `backend/application/cash_register/overview_query_service.py`, `shift_query_service.py`, `backend/infrastructure/integrations/finance_close_sources.py`, `backend/infrastructure/db/repositories/organization/org_unit_repository.py`, `backend/infrastructure/db/repositories/software_updates/station_update_repository.py` | Estados desde la política (placeholders); Finanzas cuenta con el resolvedor; Organización deja de contar `CANCELLED` | quitar `expectedFailure` de la prueba de Organización → pasa; segmentos Organización/Actualizaciones/Finanzas |
| 7 | `tests/architecture/test_active_shift_single_source.py` (nuevo) | Guardia (a)–(d) del criterio 8 | la guardia pasa; se comprueba que detecta una violación sembrada en un archivo temporal |

## Archivos que NO se tocan
- Shims intencionales de `CLAUDE.md` (finanzas, WhatsApp): sin relación.
- `migrations/standalone/175_cash_register_bounded_context_schema.py`: sus índices `ux_cash_shift_active_*` (234-237) son la garantía en esquema; no se cambia esquema.
- `frontend/desktop/modules/cash_register/cash_shifts_page.py:98-99`: el renglón seleccionado es el destino explícito de una acción, validado por el backend (`shift_use_cases.py:117-128`); no es resolución de turno activo.
- `active_cash_count_id` / `active_cash_register_id` del `composition_root`: no son turno activo; fuera de alcance.
- Distinguir falla de esquema de "sin turno" (SDLC-SALES-007), consulta del gerente (SHIFT-002), concurrencia/incompatibilidad (SHIFT-004).

## Migraciones
Ninguna (no se usa el número 355).

## Criterio de terminado
| Criterio spec | Prueba |
|---|---|
| 1 OPEN | `test_active_shift_coherence.py::ActiveShiftCoherenceTests::test_open_shift_is_the_same_for_caja_pos_and_finance` |
| 2 SUSPENDED | `::test_suspended_shift_is_still_the_cashiers_shift_but_cannot_sell`, `ActiveShiftDivergenceTests::test_pos_tells_the_cashier_to_resume_a_suspended_shift` |
| 3 CLOSING | `::test_closing_shift_is_shown_by_caja_and_counted_but_cannot_sell`, `::test_closed_shift_is_returned_by_nobody_and_a_new_one_can_be_opened`, `::test_pos_tells_the_cashier_to_finish_closing_and_open_a_new_shift` |
| 4 sin turno | `::test_no_shift_everyone_agrees`, `test_active_shift_resolver.py` (sin tabla) |
| 5 sin caché | `::test_composition_root_holds_no_active_shift_cache` |
| 6 unicidad | sin cambio de esquema (la migración 175 no se toca) |
| 7 recuentos | `::test_other_contexts_count_only_non_final_shifts`, `::test_cancelled_shift_is_final_for_organization` |
| 8 guardia | `tests/architecture/test_active_shift_single_source.py` |
| 9 sin regresiones | segmentos de la línea base |
