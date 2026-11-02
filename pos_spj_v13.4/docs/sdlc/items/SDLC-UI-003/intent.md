# SDLC-UI-003 — Guardia de deuda visual en rojo: línea base del 2026-09-10 con 17 hallazgos nuevos y 26 resueltos sin podar

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §42, §45.26 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-30, Alfred)
- **Depende de:** —

## Problema
La guardia global del Design System falla en sus dos pruebas, así que el paso de arquitectura de CI está en rojo y ya no puede distinguir una regresión nueva de la deuda vieja. Hay 17 hallazgos que no están en la línea base y 26 entradas de la línea base que ya se resolvieron y no se quitaron. Las 4 tablas nativas de Finanzas y Cárnico nunca entraron a la línea base.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- *medido:* `python -m pytest tests/architecture/test_design_system_guardrails.py` → falla `test_desktop_visual_debt_does_not_grow` y `test_visual_debt_baseline_is_exact_and_kept_pruned`
- *medido:* `design_system_audit.regressions()` → nuevos: 13 `screen_without_explicit_overflow` (`customers_crm/pages/_work_items.py`, `_workbench.py`, `customer_sections.py`×2, `leads_pages.py`, `opportunity_pages.py`×3, `service_pages.py`, `configuracion/pages/actualizaciones_page.py`, `finance/pages/overview_page.py`, `meat_processing/pages/meat_processing_settings_page.py`, `pricing/pages/settings_page.py`) y 4 `native_operational_table`; resueltos sin podar: 13 `unicode_icon_literal` y 13 overflow de `*_view.py`
- `tests/architecture/design_system_debt_baseline.json` (`captured_on` 2026-09-10, `last_pruned_on` 2026-09-11)
- `../.github/workflows/ci-segmented.yml:32-35` corre `tests/architecture`

## Impacto
Mientras la guardia esté en rojo, cualquier PR de UI pasa con la misma falla y la deuda puede crecer sin que nadie lo note.

## Objetivo
- Las entradas resueltas se podan de la línea base
- Los 17 hallazgos nuevos se corrigen, o se registra por qué entran a la línea base con aprobación explícita del responsable (la política del archivo lo prohíbe por defecto)
- `test_design_system_guardrails.py` en verde

## Alcance
- **Incluye:** Poda de la línea base y decisión sobre los 17 nuevos.
- **No incluye:** Ampliar las reglas de la auditoría (SDLC-UI-029); migrar las 4 tablas (SDLC-UI-025).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
SDLC-CORE-009 (triage 2026-10-28) lista `test_design_system_guardrails.py` (2) entre las guardias en rojo; esta parte queda cubierta aquí.

## Preguntas abiertas
- ¿Se autoriza meter a la línea base los 17 hallazgos nuevos para volver a verde y corregirlos después en sus ítems (UI-010, UI-025)? si
