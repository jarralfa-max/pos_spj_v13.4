# SDLC-FIN-004 — La depreciación mensual solo se corre a mano: la corrida automática del legacy se perdió al borrarlo

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §4, §33 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-FIN-003

## Problema
El sistema legacy depreciaba cada mes de forma automática (un job el día 1 que recorría todas las sucursales). Al borrar `core/app_container.py` y `AssetService`, esa automatización desapareció sin reemplazo. Hoy alguien tiene que entrar a Finanzas → Depreciación y correrla; si no lo hace, el cierre de periodo se bloquea. No hay aviso previo ni corrida programada.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `frontend/desktop/modules/finance/pages/depreciation_page.py:35` → `finance_presenter.py:970` → `finance_routes.py:269` → `RunDepreciationUseCase` — única vía
- `backend/application/services/finance/period_close_checklist.py:38-41,86,108` — el cierre bloquea si falta depreciación
- No hay referencias a depreciación en schedulers, ciclos de fondo, `backend/api` ni `scripts/` (barrido del subagente A)
- Legacy: el job mensual que llamaba `accrual_depreciacion_mensual()` se documentó en `docs/refactor/ASSET-22_migracion_consumidores.md` (histórico, no evidencia de código)

## Impacto
Finanzas: trabajo manual mensual y riesgo de que el cierre se trabe al último día. Es funcionalidad operativa perdida (CLAUDE.md, prioridad 0).

## Objetivo
- La depreciación del periodo se corre sola (o se avisa con anticipación) sin intervención, de forma idempotente por periodo.
- Prueba: dos disparos del mismo periodo producen una sola corrida.

## Alcance
- **Incluye:** Disparador de la corrida en el ciclo de fondo existente o aviso en la bandeja; idempotencia por periodo.
- **No incluye:** Nuevos métodos de depreciación (DECLINING_BALANCE etc., §35), que no se piden como brecha urgente.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- SDLC-CORE-006 (suma de la corrida con la moneda del primer activo)
- Memoria CRM-43 (ciclo de fondo y campana ya cableados)

## Preguntas abiertas
- ¿La depreciación debe correr sola el día 1, o basta un aviso en la bandeja de Finanzas para que la corra una persona? sola en el dia 1
