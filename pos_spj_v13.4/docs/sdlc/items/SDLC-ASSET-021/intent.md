# SDLC-ASSET-021 — Inspecciones y checklists configurables sin persistencia, casos de uso ni pantalla

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §37, §38, §67 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** SDLC-ASSET-016, SDLC-ASSET-009

## Problema
Inspecciones, plantillas de checklist y resultados existen solo como entidades. Un resultado OUT_OF_SERVICE no cambia el estado del activo ni genera OT.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/entities/asset_inspection.py:30-79`
- `backend/domain/assets/entities/inspection_checklist_template.py:15-61`

## Impacto
No hay registro de inspecciones de seguridad ni de calidad de equipos (básculas, refrigeración).

## Objetivo
- Casos de uso de §67; inspección fallida crea OT; plantillas configurables.
- Pantalla de inspecciones; pruebas de integración.

## Alcance
- **Incluye:** Inspecciones y plantillas.
- **No incluye:** Calidad de producto (contexto Calidad).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- ASSET-7

## Preguntas abiertas
- Ninguna por ahora.
