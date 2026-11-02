# SDLC-FIN-003 — Baja o venta de activo fijo no exige depreciación al día y sus casos de uso no tienen pruebas

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §33, §46, §47 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`DisposeAssetUseCase` calcula el valor en libros y la utilidad o pérdida con la depreciación acumulada que tenga el activo, sin verificar que se haya corrido hasta el periodo de la baja. Si faltan meses, la baja sale con un valor en libros mayor y una pérdida inflada (o una ganancia menor), y esos meses ya no se pueden depreciar porque el activo queda dado de baja. Ni `DisposeAssetUseCase` ni `ChangeAssetStatusUseCase` tienen una sola prueba, aunque mueven dinero (cobro a tesorería y utilidad o pérdida).

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/application/use_cases/finance/dispose_asset_use_case.py:57-69` — usa `asset.net_book_value()` sin comparar `last_depreciated_period` con la fecha de baja (*verificado directamente*)
- `backend/application/use_cases/finance/dispose_asset_use_case.py:114-138` — `ChangeAssetStatusUseCase`
- `backend/domain/finance/entities/fixed_asset.py:189-201` — `register_depreciation` y `net_book_value` (*verificado directamente*)
- `backend/domain/finance/policies/depreciation_policy.py:28-31` — decisión documentada: los meses omitidos no se recuperan a mitad de vida (*verificado directamente*)
- `frontend/desktop/modules/finance/pages/fixed_assets_page.py:81-93` → `finance_routes.py:270-271` — llamadores reales
- Ninguna prueba en `tests/` referencia `DisposeAssetUseCase` ni `ChangeAssetStatusUseCase` (barrido de los subagentes B, C y D)

## Impacto
Contabilidad: resultado por disposición incorrecto en cada baja o venta hecha con depreciación atrasada. Frecuencia baja, pero sin red de pruebas cualquier cambio en el motor puede romper la baja sin que nadie lo note.

## Objetivo
- La baja exige depreciación corrida hasta el periodo anterior al de la baja (o la corre / la bloquea con mensaje claro, según decida el responsable).
- Pruebas de regresión de baja por venta (con y sin ganancia), baja por desecho, suspensión y reactivación, con balanza cuadrada.
- Prueba de la idempotencia ya existente (`disposal_journal_entry_id`).

## Alcance
- **Incluye:** Casos de uso de baja y cambio de estado de Finanzas, sus pruebas.
- **No incluye:** El flujo de solicitud/aprobación del EAM (SDLC-ASSET-026); corrida automática mensual (SDLC-FIN-004).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- Auditoría F19 (cuota del último mes) en `depreciation_policy.py`

## Preguntas abiertas
- Si a la baja le faltan meses de depreciación: ¿se bloquea, o el caso de uso deprecia los meses faltantes antes de dar de baja?
- La regla actual «meses omitidos no se recuperan a mitad de vida; el último mes liquida» (`depreciation_policy.py:28-31`), ¿se mantiene o se prefiere recuperar en el siguiente periodo corrido?
