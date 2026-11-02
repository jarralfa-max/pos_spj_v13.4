# SDLC-ASSET-035 — Inventarios de documentación de Activos (§4) faltantes o desactualizados

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/activos.md` §4, §114 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
§4 pide 7 inventarios; existen 2 (`assets_legacy_inventory.md`, `assets_finance_boundary_map.md`) y describen un legacy que ya se borró. `MIGRATION_LOG.md:2998` afirma un escritor vivo que ya no existe.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `docs/refactor/` — solo `assets_finance_boundary_map.md` y `assets_legacy_inventory.md` (*verificado directamente*)
- `migrations/MIGRATION_LOG.md:2998` (*verificado directamente*)

## Impacto
Documentación que engaña a quien retome el módulo.

## Objetivo
- Inventarios actualizados contra el código actual (puede servir de base `docs/sdlc/arquitectura/matriz-activos.md`).

## Alcance
- **Incluye:** Documentos de §4.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
- ASSET-0..24

## Preguntas abiertas
- Ninguna por ahora.
