# SDLC-ASSET-025 — Inventario físico de activos sin persistencia, escaneo ni resolución de diferencias

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §44, §45, §69 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** SDLC-ASSET-027, SDLC-ASSET-009, SDLC-ASSET-014

## Problema
El conteo físico con escaneo QR o código de barras y el flujo de diferencias existen solo como entidades. No hay forma de resolver un código escaneado a un activo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/entities/asset_physical_inventory.py`, `asset_physical_inventory_line.py:24-35`, `asset_physical_discrepancy.py`

## Impacto
No hay control físico de activos.

## Objetivo
- Casos de uso de §69 con escaneo idempotente y diferencias que no se corrigen solas.
- Pantalla de conteo; pruebas.

## Alcance
- **Incluye:** Inventario físico y diferencias.
- **No incluye:** Modo offline (SDLC-ASSET-032).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- ASSET-11

## Preguntas abiertas
- Ninguna por ahora.
