# SDLC-ARQ-SESS-003 — Una venta suspendida puede reanudarla otro usuario y queda atribuida al cajero original

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §7 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R7.3 Operaciones abiertas aisladas por usuario, estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`ResumeSaleUseCase` permite por defecto reanudar ventas de otro usuario y de otra estación (`allow_cross_user_resume=True`, `allow_cross_workstation_resume=True`); el presentador no lo restringe. `cashier_user_id` no se reasigna, así que el cobro queda atribuido al cajero original. El documento pide que operaciones abiertas no se atribuyan al siguiente usuario y que transferirlas requiera flujo explícito, permiso y auditoría.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sales/use_cases/lifecycle_use_cases.py:90-94` (*verificado directamente*)
- `backend/domain/sales/entities.py:499-514`
- `frontend/desktop/modules/sales_pos/sales_pos_presenter.py:474-477`
- Pruebas: `tests/unit/test_sales_suspension.py` (sólo banderas).

## Impacto
Efectivo cobrado por un usuario aparece en las ventas de otro; faltantes de caja no atribuibles.

## Objetivo
- Por defecto sólo el cajero original reanuda.
- Reanudar una venta ajena exige permiso específico, reasigna el responsable y audita el traspaso.
- Pruebas de integración.

## Alcance
- **Incluye:** Caso de uso, presentador, permiso, auditoría.
- **No incluye:** Expiración de suspendidas (SDLC-SALES-004).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SALES-004.

## Preguntas abiertas
- ¿Se permite que un supervisor reanude ventas de otro cajero? ¿y que otro cajero las tome con autorización?
