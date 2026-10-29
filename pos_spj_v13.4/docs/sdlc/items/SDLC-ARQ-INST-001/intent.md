# SDLC-ARQ-INST-001 — Actualizar con el Setup manual o 'Reparar' migra la base al arrancar sin respaldo previo

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §13 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R13.4 / R13.6 Sin migración sin respaldo, estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Sólo el camino del actualizador respalda la SQLite antes de migrar. Si se ejecuta el instalador a mano o el atajo 'Reparar', las migraciones corren en el siguiente arranque sin respaldo (`run_database_bootstrap.py`, `database_migration_step.py`). El documento prohíbe migraciones sin respaldo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/bootstrap/run_database_bootstrap.py`; `backend/bootstrap/steps/database_migration_step.py` (sin respaldo, según barrido; **no verificado** línea por línea)
- Contraste: `backend/application/software_updates/update_transaction.py:98-257` (sí respalda)
- Pruebas: `tests/integration/bootstrap/test_main_startup_gates.py::test_failed_migration_exits_before_setup_or_login` (no cubre respaldo).

## Impacto
Una migración fallida tras actualización manual puede dejar la base de la sucursal irrecuperable: pérdida de ventas, caja y cola de sync.

## Objetivo
- Antes de aplicar migraciones pendientes al arrancar se toma un respaldo verificado (mismo mecanismo que el actualizador).
- Si el respaldo falla, no se migra y se explica.
- Prueba de integración con migración que falla → base restaurable.

## Alcance
- **Incluye:** Paso de migración del arranque.
- **No incluye:** Respaldo de configuración/secretos (ARQ-INST-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-INST-001..003.

## Preguntas abiertas
- Ninguna por ahora.
