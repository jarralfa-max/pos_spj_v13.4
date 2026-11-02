# SDLC-UI-025 — Finanzas y Cárnico: 4 QTableWidget (asiento contable editable incluido) e inputs nativos

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §36, §39, §46.23 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-019, SDLC-UI-020

## Problema
El diálogo de asiento contable, el de presupuesto, el de cobranza y el plan de Cárnico usan `QTableWidget` editable, fuera de `StandardTable`. Finanzas usa además 11 `QLineEdit` y 10 `QComboBox` nativos. En el asiento, la tabla captura los renglones de debe y haber.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/finance/dialogs/journal_entry_dialog.py:68`; `budget_dialog.py:46`; `collection_dialog.py:61`
- `frontend/desktop/modules/meat_processing/dialogs_plan.py:120`
- *medido:* las 4 son hallazgos `native_operational_table` nuevos frente a la línea base

## Impacto
Contadores: captura de asientos con una tabla sin densidad táctil ni contrato. Cualquier migración aquí toca la captura de dinero, de ahí el nivel T1.

## Objetivo
- Las 4 tablas usan `StandardTable` o un componente canónico editable
- Prueba de regresión del asiento antes de migrar: los renglones capturados producen el mismo comando (debe = haber)

## Alcance
- **Incluye:** Los 4 diálogos y los inputs nativos de `modules/finance`.
- **No incluye:** Reglas contables.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- ¿`StandardTable` debe soportar edición en celda, o se crea un `EditableTable` canónico? EditableTable canonico
