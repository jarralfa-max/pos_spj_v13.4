# SDLC-LOY-001 — Cupones nunca expiran (ExpireCouponsUseCase sólo en pruebas)

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`ExpireCouponsUseCase` sólo se llama desde pruebas; los cupones no expiran y el valor no usado nunca se reconoce.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/commercial_instruments/use_cases/coupon_use_cases.py:265`

## Impacto
Pasivo de cupones sobrestimado.

## Objetivo
- Expiración programada en el ciclo periódico con asiento de breakage si aplica.

## Alcance
- **Incluye:** —
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
LOY-29.

## Preguntas abiertas
- ¿Se reconoce breakage contablemente?
