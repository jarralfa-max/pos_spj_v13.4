# SDLC-PROC-002 — Disponibilidad para producción suma piezas como kg y con REAL

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`lots` suma `inventory_balances.quantity` con `CAST(... AS REAL)` y lo presenta como `available_kg`: piezas no equivalen a kg y REAL pierde precisión Decimal. El ledger de transferencias sí distingue cantidad y peso observados.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/meat_processing/queries/direct_transformation_query_service.py:132` *(verificado directamente en el triage)*
- Auditoría 2026-10-26 §3 P0 #4

## Impacto
Despieces calculados sobre kg incorrectos.

## Objetivo
- Disponibilidad en la unidad base del producto con Decimal y conversión explícita.
- Sin peso neto para un perfil en kg, el despiece automático se bloquea y pide pesaje.

## Alcance
- **Incluye:** Consulta de disponibilidad.
- **No incluye:** Otros REAL (CORE-007).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
Auditoría 2026-10-26.

## Preguntas abiertas
- Ninguna por ahora.
