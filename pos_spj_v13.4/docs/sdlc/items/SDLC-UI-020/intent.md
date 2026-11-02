# SDLC-UI-020 — MoneyInput guarda montos en float (QDoubleSpinBox)

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §39 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
El input canónico de dinero se apoya en un `QDoubleSpinBox`, así que el valor capturado es un float binario antes de llegar a los casos de uso. El resto del sistema maneja dinero en `Decimal`. Además, los placeholders no tienen estilo propio y `FormField` (label, ayuda y error) se usa solo 45 veces.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/components/money_input.py`; `frontend/desktop/components/numeric_input.py:13`
- `frontend/desktop/components/form_field.py:28-80`
- `frontend/desktop/themes/qss_builder.py:288-314` (sin regla de placeholder)
- Conversión del float a Decimal en cada llamador: **no verificado** caso por caso

## Impacto
Montos capturados en caja, cobros, gastos y compras pueden llegar con error de representación si un llamador no redondea al convertir.

## Objetivo
- `MoneyInput` expone y emite `Decimal` cuantizado a centavos
- Una prueba captura valores como 0.1 + 0.2 y 1234567.89 sin error
- Los llamadores que usaban `.value()` como float quedan migrados

## Alcance
- **Incluye:** `money_input.py`, `numeric_input.py` y sus llamadores.
- **No incluye:** Float residual en backend (SDLC-CORE-006).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
SDLC-CORE-006 (float residual en dinero en backend); SDLC-SALES-002 (redondeo a centavos).

## Preguntas abiertas
—
