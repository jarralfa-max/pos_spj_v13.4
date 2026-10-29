# SDLC-ARQ-SHIFT-004 — Transiciones de turno sin control de concurrencia y apertura no idempotente

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §8 · §12 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R8.6/R8.8 Turnos incompatibles y concurrencia, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-SHIFT-001

## Problema
`set_lifecycle` actualiza el estado del turno con `WHERE id=?` sin comprobar el estado actual; `cash_shifts` no tiene columna de versión; la unidad de trabajo abre `BEGIN` diferido en vez de `BEGIN IMMEDIATE`. Un reintento de `OpenCashShiftUseCase` con el mismo `operation_id` falla con 'ya tiene turno' en lugar de devolver el turno existente. No hay ninguna prueba concurrente de Caja. El cierre doble sí está protegido (UPDATE condicionado + índice único de Z final).

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/db/repositories/cash_register/repositories.py:58-61` (*verificado directamente*)
- `backend/infrastructure/db/transaction.py:103`
- `backend/infrastructure/db/repositories/cash_register/repositories.py:94-100` (cierre sí condicionado)
- `backend/application/cash_register/shift_use_cases.py:69-80`
- Pruebas: `tests/integration/cash_register/test_z_cut_finalization_flow.py:111`, `test_cash_ledger_flow.py:136`; concurrentes de caja: ninguna (`tests/test_fase_g_concurrency.py` cubre inventario y folios).

## Impacto
Dos acciones simultáneas (suspender y preparar cierre, reanudar y forzar cierre) pueden dejar el turno en un estado que ninguna regla de dominio permite. Un reintento de apertura tras timeout se ve como error al cajero.

## Objetivo
- Toda transición de turno es compare-and-set sobre estado y versión; 0 filas afectadas se reporta como conflicto.
- Abrir turno con un `operation_id` ya aplicado devuelve el resultado original.
- Pruebas concurrentes (dos conexiones) de suspender/cerrar/reanudar respetan las invariantes (§15 T9 para caja).

## Alcance
- **Incluye:** Versión en `cash_shifts` (migración), repositorio, unidad de trabajo, pruebas concurrentes.
- **No incluye:** Detección central de dos turnos abiertos desde estaciones distintas (SDLC-ARQ-SYNC-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Regla vigente de 'turnos incompatibles': ¿uno por caja, por cajón, por cajero o por terminal? (hoy hay índices únicos parciales para los cuatro)
