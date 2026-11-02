# SDLC-UI-006 — Quedan glifos Unicode como icono (⌨ ⌫ →) y la guardia no cubre ese rango

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §11 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-003

## Problema
La mayoría de los glifos ya se reemplazaron por SVG, pero el teclado numérico usa ⌨ y ⌫, y el selector de rango de horas y el tablero de compras usan → como separador. La guardia no los detecta porque su regex solo cubre U+2600–27BF y U+1F300+.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/components/numeric_keypad_dialog.py:101,242` (⌨), `:122,131` (⌫)
- `frontend/desktop/components/time_range_input.py:31` (→)
- `frontend/desktop/modules/purchasing/pages/procurement_dashboard_page.py:151` (→)
- `tests/architecture/design_system_audit.py:21` (`EMOJI` no incluye U+2190–23FF ni ×)

## Impacto
Iconos que dependen de la fuente instalada y no siguen el tema; deuda que la guardia no ve.

## Objetivo
- Los cuatro usos se reemplazan por iconos de `IconProvider` (`Icons.*`)
- La regex de la guardia cubre flechas, símbolos técnicos y ×, sin marcar texto en prosa

## Alcance
- **Incluye:** Los 4 archivos y la regex.
- **No incluye:** —

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
