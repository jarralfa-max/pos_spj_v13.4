# SDLC-UI-027 — Accesibilidad: sin orden de tabulación, nombres accesibles sin guardia y estado por color sin prueba

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §41 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
El foco es visible, el contraste está vigilado y el tamaño táctil también. Pero ninguna pantalla define orden de tabulación (`setTabOrder` 0), los nombres accesibles no tienen guardia, y que el estado no dependa solo del color no se prueba.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- *medido por el barrido:* `setTabOrder` 0 usos en `frontend/desktop`
- `setAccessibleName`: 42 en componentes, 368 en módulos; sin guardia
- `frontend/desktop/themes/qss_builder.py:183,197,274,302` (foco visible)
- `tests/architecture/test_theme_contrast.py`; `tests/ui/test_density_control_targets.py`

## Impacto
Usuarios de teclado en caja y administración; lectores de pantalla.

## Objetivo
- Orden de tabulación definido en formularios y en el POS
- Guardia: controles interactivos sin nombre accesible ni texto visible fallan
- Prueba de que los badges de estado llevan texto o icono además del color

## Alcance
- **Incluye:** Componentes canónicos y guardias.
- **No incluye:** Certificación WCAG.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
