# SDLC-BI-003 — Dos motores de pronóstico dan números distintos para lo mismo

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El tablero ejecutivo usa promedio móvil de 7 días sobre ingreso en float; la página de Pronóstico usa `demand_planning_service` (modelos y backtests).

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/analytics/queries/bi_forecast_query_service.py:1-5,34-40`
- `backend/application/forecasting/services/demand_planning_service.py`

## Impacto
Pronósticos contradictorios.

## Objetivo
- Un motor de pronóstico; el tablero consume el mismo servicio.

## Alcance
- **Incluye:** BI.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
BI-33.

## Preguntas abiertas
- Ninguna por ahora.
