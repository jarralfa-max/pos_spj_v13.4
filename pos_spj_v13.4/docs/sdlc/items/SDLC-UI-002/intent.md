# SDLC-UI-002 — 106 fallas en tests/ui: layout de módulo, iconos del sidebar de Finanzas y secciones de Productos

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §9, §15, §43 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-30, Alfred)
- **Depende de:** SDLC-UI-001

## Problema
Antes del corte de la suite fallan 96 pruebas. Las 92 de `test_module_layout.py` muestran que al menos una pantalla real (Precios) ya no declara su variante de layout. Las de sidebar muestran que Finanzas perdió la sección «Resumen financiero» y que Productos tiene 14 entradas en vez de las 7 que el contrato espera. Puede ser regresión de la UI o prueba desactualizada; hay que decidirlo caso por caso.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- *medido:* 92 fallas en `tests/ui/test_module_layout.py` (`test_module_layout_at_supported_resolutions`, `test_module_layout_rejects_undefined_or_contradictory_variants`); la primera: `PricingWorkspace.property('moduleLayoutVariant')` es `None`, se esperaba `'standard'`
- *medido:* `tests/ui/test_finance_hr_sidebar_icons.py::test_module_sidebar_keeps_semantic_icons_and_page_destinations[light|dark-finance…]` → `KeyError: 'Resumen financiero'`
- *medido:* `tests/ui/test_operational_sidebar_icons.py::test_products_real_composition_has_distinct_section_icons` → `assert 14 == 7` (`ProductsView.nav.count()`)
- *medido:* `tests/ui/test_operations_standard_dialogs.py::test_payment_enter_adds_local_line_and_cancel_never_starts_checkout`

## Ampliación (SDLC-UI-001, decisión D4)
Con la suite completa terminando (SDLC-UI-001, 2026-10-31) aparecieron 10 fallas que antes no corrían. Se suman aquí: el total pasa de 96 a 106.

- *medido:* `tests/ui/test_shell_prompt_adoption.py::test_reason_actions_preserve_validation_and_payload` (3 casos de `BankReconciliationPage._revert`) → `TypeError` en `frontend/desktop/components/dialogs.py:39`: el doble pasa un `SimpleNamespace` como `parent` de `QDialog`
- *medido:* `tests/ui/test_shell_prompt_adoption.py::test_reconciliation_difference_retries_only_after_a_valid_reason` (3 casos) → `AttributeError` en `frontend/desktop/modules/finance/pages/bank_reconciliation_page.py:189`: el doble no tiene `selected_id`
- *medido:* `tests/ui/test_shell_prompt_adoption.py::test_receivable_prompt_preserves_customer_selection` (3 casos) → `tests/ui/test_shell_prompt_adoption.py:72`: `AccountsReceivablePage` ya no tiene `_show_crm_summary` (hoy existe `show_crm_summary_for`)
- *medido:* `tests/ui/test_page_stack.py::test_pricing_cached_large_page_does_not_enlarge_returned_small_page` → `AssertionError` en `tests/ui/test_page_stack.py:45`

La intermitencia de `tests/ui/test_standard_window_geometry.py::test_screen_change_rebinds_available_area_and_disconnects_previous` no entra aquí: va en SDLC-UI-031.

## Impacto
Las pruebas que vigilan responsive y navegación están en rojo, así que no detectan regresiones nuevas.

## Objetivo
- Cada una de las 106 fallas queda clasificada como regresión (se corrige la UI) o prueba desactualizada (se corrige la prueba), con la decisión en el plan
- `tests/ui` sin fallas de aserción

## Alcance
- **Incluye:** Las 4 familias de fallas medidas y las 10 de la ampliación.
- **No incluye:** El cierre del proceso (SDLC-UI-001); fallas que aparezcan en las 487 pruebas que hoy no corren (se agregan aquí o en un ítem nuevo cuando SDLC-UI-001 las destape).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- Productos con 14 secciones en el sidebar: ¿es el diseño vigente (y la prueba está vieja) o se esperaba agrupar en 7? 14 secciones 
