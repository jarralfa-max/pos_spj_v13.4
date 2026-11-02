# SDLC-ASSET-028 — Compras no solicita el registro de activos de capital al recibir

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §52 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** SDLC-FIN-002, SDLC-ASSET-011

## Problema
Compras ya clasifica compras con naturaleza ASSET, pero al recibirlas no pide a Activos que cree el activo en borrador para completar sus datos. El evento `ASSET_REGISTRATION_REQUESTED` no existe en el código.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/procurement/enums.py:38,100` — `PurchaseNature.ASSET`, `DIRECT_ASSET`
- `backend/application/procurement/integrations/downstream_events.py:12-19`, `downstream_translators.py:66-158` — sin activos

## Impacto
Cada equipo comprado hay que capturarlo de nuevo a mano.

## Objetivo
- Recepción de un ítem de capital → solicitud de registro → activo en borrador, con política (no un activo por cada compra; cantidad y categoría).
- Pruebas de integración.

## Alcance
- **Incluye:** Evento, política y consumidor en Activos.
- **No incluye:** Reconocimiento contable (SDLC-FIN-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- Memoria Compras PUR-AUD (eventos de compensación sin consumidor)

## Preguntas abiertas
- ¿Una línea de compra con cantidad 5 genera 5 activos en borrador, o un borrador que se desdobla al capturar series?
