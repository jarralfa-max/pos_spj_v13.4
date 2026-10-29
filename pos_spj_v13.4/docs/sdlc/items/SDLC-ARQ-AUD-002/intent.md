# SDLC-ARQ-AUD-002 — Auditoría fragmentada sin esquema común; actor por defecto 'Sistema' y sin terminal ni resultado

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §14 · §7 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R7.4 / R14.1 Actor real, terminal, ámbito, resultado, estado `duplicado`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-TERM-001

## Problema
Hay tres tablas generales (`audit_logs`, `audit_log`, `auditoria_eventos`) y ~15 por módulo con columnas distintas. El escritor canónico guarda el actor como nombre libre con valor por defecto 'Sistema', no tiene columna de terminal ni de resultado y mete `operation_id` en el texto de `detalles`. Una prueba fija 'Sistema' como actor aceptable.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `migrations/m000_base_schema.py:2386-2399`; `migrations/standalone/063_audit_log_table.py:10`; `066_erp_financial_model.py:235`
- `backend/infrastructure/db/repositories/settings/audit_log_repository.py:75-84`
- `backend/application/shared/audit_trail.py:42-76`
- `tests/integration/shared/test_audit_trail.py::test_an_operation_without_an_actor_is_still_attributable`

## Impacto
No se puede responder 'quién, qué, cuándo, terminal, ámbito, operación, resultado' de forma uniforme.

## Objetivo
- Contrato común de evento de auditoría (actor id, terminal id, ámbito, recurso, operation_id, resultado).
- Acciones sin actor se rechazan salvo procesos de sistema identificados.
- Plan de convergencia de tablas por módulo (sin lectura/escritura dual).

## Alcance
- **Incluye:** Contrato, escritor canónico, migración.
- **No incluye:** Migrar todos los módulos en un PR.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
