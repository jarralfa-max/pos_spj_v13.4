# SDLC-CORE-010 — 4 fallas en tests/unit: permiso de aprobar flags, diálogo de cobro y barra lateral de Transferencias

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`tests/unit` (6182) tiene 4 fallas: dos de Feature Flags porque el usuario de prueba no tiene `CONFIGURACION.flag.aprobar`; una del POS que parchea `QtWidgets.MessageDialog` (inexistente; probable prueba desactualizada tras reemplazar QMessageBox); y la barra lateral de Transferencias, que muestra 0 entradas donde la prueba espera 2 (**no verificado** si es prueba desactualizada o regresión; el último commit `16eb1d8e` tocó páginas de Transferencias).

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `docs/sdlc/baseline/2026-10-28.md` — `4 failed, 6178 passed in 789.72s` *(verificado directamente en el triage)*
- `tests/unit/test_feature_flags_page.py` (`TestFeatureFlagsPageLoadsRealData::test_selecting_a_flag_loads_its_rules`, `TestFeatureFlagsFullLoop::test_create_request_approve_apply_closes_the_loop`) — `no tiene el permiso CONFIGURACION.flag.aprobar` *(verificado directamente en el triage)*
- `tests/unit/test_pos_checkout_dialogs.py::test_reintentar_el_cobro_no_duplica_pagos` — `module 'PyQt5.QtWidgets' has no attribute 'MessageDialog'` *(verificado directamente en el triage)*
- `tests/unit/test_transfers_ui_workspace.py:64-67` — `assert 0 == 2` *(verificado directamente en el triage)*

## Impacto
Si alguna es regresión: aprobación de flags rota, o menú de Transferencias vacío para usuarios con permiso parcial. Si no, la prueba anti-doble-cobro dejó de proteger.

## Objetivo
- Cada falla clasificada (prueba desactualizada vs regresión) con evidencia; la prueba anti-doble-cobro vuelve a ejercitar el flujo real.
- Suite `tests/unit` verde.

## Alcance
- **Incluye:** Las 4 pruebas y, si hay regresión, su corrección mínima.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
PERM-AUD (migr. 347: códigos punteados), UI Design System (MessageDialog).

## Preguntas abiertas
- Ninguna por ahora.
