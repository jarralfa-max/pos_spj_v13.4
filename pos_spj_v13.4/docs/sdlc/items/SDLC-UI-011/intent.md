# SDLC-UI-011 — Layouts canónicos que solo existen de nombre (FormPage, MasterDetailPage, POSPage, Toast) y WizardPage duplicado

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §6, §7 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-007, SDLC-UI-010

## Problema
El catálogo registra los 59 componentes, pero varios son una clase vacía. `FormPage` no tiene ni formulario ni acciones fijas propios, `MasterDetailPage` es igual a `SplitPage`, `ScrollablePage` está vacío y `POSPage` solo pone una propiedad que nadie lee. `Toast` no se superpone y `NavItem`/`NavGroup` son items de lista. Además hay un segundo `WizardPage` en el asistente de instalación. Sin estos layouts, los módulos no pueden migrar a una estructura estándar.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/components/pages.py:58,62,88,104`
- `frontend/desktop/components/view_states.py:79` (`Toast`)
- `frontend/desktop/components/side_nav.py:20,24`
- `frontend/desktop/provisioning/pages/_wizard_page.py:16` (duplicado)
- Adopción en módulos: FormPage 1 archivo; DashboardPage, POSPage, WizardPage, SplitPage, MasterDetailPage y ScrollablePage, 0
- `tests/ui/test_design_system_registry.py` (solo comprueba que existan)

## Impacto
Cada módulo arma su propia estructura (149 clases `QWidget`/`QFrame` a mano), así que ninguna regla de layout se puede aplicar.

## Objetivo
- `FormPage` con formulario con scroll y acciones fijas; `MasterDetailPage` con master y detalle; `POSPage` con densidad TOUCH real; `Toast` superpuesto y temporal
- Un solo `WizardPage`
- Pruebas de comportamiento de cada layout, no solo de existencia

## Alcance
- **Incluye:** `frontend/desktop/components/` y el asistente de provisión.
- **No incluye:** Migrar pantallas de módulos (SDLC-UI-023…026).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
