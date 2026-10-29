# SDLC-PROC-003 — Asiento de costo de producción fallido espera a la siguiente orden

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`costing_outbox` (asiento de producción y merma de proceso) se despacha sólo justo después de ejecutar una orden; a diferencia de Compras, RRHH, Caja y Mermas no tiene reintento al arrancar ni periódico.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/desktop/meat_processing_factory.py:74-80`
- `backend/application/costing/wiring.py:45`
- `backend/bootstrap/wiring/event_wiring.py:93-126`

## Impacto
Costos de producción ausentes del mayor por días.

## Objetivo
- `costing_outbox` en el ciclo de arranque y periódico.

## Alcance
- **Incluye:** Tarea periódica.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
PROC-AUD.

## Preguntas abiertas
- Ninguna por ahora.
