# SDLC-ASSET-015 — Transferencias de activos entre sucursales sin persistencia ni flujo

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §20, §65 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-011, SDLC-ASSET-008, SDLC-ASSET-007

## Problema
El flujo solicitar → aprobar → preparar → enviar → recibir existe solo como entidad. No hay casos de uso, tablas ni pantalla, y hoy la única forma de cambiar un activo de sucursal sería `relocate()`, que §20 prohíbe.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/entities/asset_transfer.py` y `enums.py:84-91`
- `backend/domain/assets/entities/asset.py:140-146`

## Impacto
No hay trazabilidad de equipos que se mueven entre sucursales.

## Objetivo
- Casos de uso Transfer/ReceiveTransferred con SoD y alcance sobre ambas sucursales.
- Pantalla de transferencias; pruebas de integración.

## Alcance
- **Incluye:** Transferencias de activos.
- **No incluye:** Transferencias de inventario (otro contexto).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- Memoria alcance: Transferencias exige alcance sobre las DOS sucursales (decisión del usuario 2026-09-17)

## Preguntas abiertas
- Ninguna por ahora.
