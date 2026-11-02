# SDLC-ASSET-023 — Las mejoras y propuestas de capitalización no tienen camino a Finanzas: Finanzas solo capitaliza activos nuevos

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §30, §31, §36, §68 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** SDLC-ASSET-011, SDLC-ASSET-008, SDLC-ASSET-024

## Problema
El legacy capitalizaba un mantenimiento sumándolo al valor del activo con un UPDATE directo (prohibido por §31). Se borró, y el reemplazo existe solo como entidad. En Finanzas no hay caso de uso para aprobar y asentar una mejora sobre un activo existente (aumentar base depreciable o vida útil): `CapitalizeAssetUseCase` solo da de alta activos nuevos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/entities/asset_improvement.py:24-55`
- `backend/domain/assets/entities/asset_capitalization_proposal.py:43-124`
- `backend/application/use_cases/finance/capitalize_asset_use_case.py:42-125` — alta de activo nuevo (*verificado directamente*)

## Impacto
Mejoras mayores se registran como gasto o no se registran.

## Objetivo
- Propuesta enviada desde Activos; Finanzas aprueba y asienta la mejora sobre el `FixedAsset` existente con asiento balanceado.
- Quien ejecuta el mantenimiento no aprueba la capitalización.
- Pruebas de extremo a extremo.

## Alcance
- **Incluye:** Mejoras, propuestas, caso de uso de Finanzas para mejoras.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- ASSET-10

## Preguntas abiertas
- ¿Una mejora capitalizada extiende la vida útil, aumenta la base, o ambas según el caso? ¿Quién aprueba en Finanzas?
