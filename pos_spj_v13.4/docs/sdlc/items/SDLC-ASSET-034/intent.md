# SDLC-ASSET-034 — Procesamiento Cárnico lleva su propio mantenimiento de equipos, paralelo al de Activos

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §115 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-016

## Problema
§115 pide una sola arquitectura de mantenimiento. Procesamiento Cárnico tiene `CompleteEquipmentMaintenanceUseCase` con su propio ciclo, que audita con `operation_id=None` y no informa a Activos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/application/meat_processing/use_cases/resource_use_cases.py:171-196`; `:193-194` `operation_id=None`

## Impacto
Dos historiales de mantenimiento del mismo equipo.

## Objetivo
- Decisión de fuente única y, si aplica, que Cárnico pida o registre el mantenimiento por Activos sin perder su lógica.

## Alcance
- **Incluye:** Mantenimiento de equipos de Cárnico.
- **No incluye:** Resto de recursos de producción.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- Memoria PROC-AUD (Procesamiento Cárnico)

## Preguntas abiertas
- ¿El mantenimiento de equipos de producción se muda a Activos, o Cárnico conserva el suyo y solo notifica a Activos? se muda
