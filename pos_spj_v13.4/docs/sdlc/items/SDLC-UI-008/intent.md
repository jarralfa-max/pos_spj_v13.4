# SDLC-UI-008 — StandardWindow no gestiona tema ni estado y la pantalla del cliente lo evita sin que la guardia lo note

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §34 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
`StandardWindow` gestiona icono, tamaño y geometría, pero no tema ni estado. La ventana de pantalla del cliente es un `QWidget` con la bandera `Qt.Window` y configura su geometría por su cuenta. La guardia de propiedad de ventanas solo busca `QMainWindow`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/components/standard_window.py:9-119`
- `frontend/desktop/modules/sales_pos/customer_display_window.py:60,81`
- `tests/architecture/test_standard_window_ownership.py` (solo `QMainWindow`)

## Impacto
Ventanas secundarias con comportamiento distinto (monitor, icono, tema); el hueco de la guardia permite más.

## Objetivo
- Toda ventana de nivel superior pasa por `StandardWindow`, o queda como excepción documentada en la infraestructura
- La guardia también detecta `QWidget` + `Qt.Window`

## Alcance
- **Incluye:** `standard_window.py`, `customer_display_window.py` y la guardia.
- **No incluye:** Rediseño de la pantalla del cliente.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
