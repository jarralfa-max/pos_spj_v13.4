# SDLC-CORE-001 — Falla en el cableado de eventos al arrancar deja la app sin integración contable, en silencio

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El cableado entre contextos se arma dentro de un solo literal de diccionario; si un `wire_*` lanza, los contextos siguientes no se suscriben y los despachos de arranque (RRHH, Compras, Caja, Ventas, Finanzas) no corren. `app.py` registra la excepción y continúa sin ningún aviso visible.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/bootstrap/wiring/event_wiring.py:62-88,93-126,224-255`
- `frontend/desktop/app.py:476-483` — `except` que registra y continúa

## Impacto
Toda la integración contable puede quedar apagada sin que nadie lo note (los outbox se acumulan).

## Objetivo
- Cada contexto se cablea de forma aislada; la falla de uno no apaga a los demás.
- Una falla de cableado es visible (aviso en el shell / salud de la app) y queda en log estructurado.
- Prueba: un `wire_x` que lanza no impide `wire_y`.

## Alcance
- **Incluye:** `event_wiring.py`, manejo en `app.py`, indicador de salud.
- **No incluye:** Reintentos periódicos de outbox específicos (SALES-003, HR-002, PROC-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria: corte del shell (cableado cruzado), ERP integration master pipeline.

## Preguntas abiertas
- Ninguna por ahora.
