# SDLC-UI-009 — StandardDialog: sin icono en encabezado, orden de botones de la plataforma y Escape implícito

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §35 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`StandardDialog` cumple casi todo el contrato: icono de ventana, encabezado, footer fijo, acción por defecto, alto máximo, scroll y tamaño táctil. Le falta el icono en el encabezado (solo `MessageDialog` lo tiene). El orden de botones lo decide la plataforma y no el estándar, y Escape solo se maneja de forma explícita en `MessageDialog`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/components/dialogs.py:42,60-115,132-157` (lo que sí cumple)
- `frontend/desktop/components/dialogs.py:347` (icono solo en `MessageDialog`), `:449` (Escape explícito solo ahí)
- `tests/architecture/test_standard_dialog_ownership.py:17-20,81-112` (0 `QDialog` directos, 0 `QInputDialog`, 2 `QMessageBox` permitidos)

## Impacto
Inconsistencia menor entre diálogos.

## Objetivo
- El orden de botones y la conducta de Escape quedan fijados por `StandardDialog` y probados
- Encabezado con icono opcional según la política de §33

## Alcance
- **Incluye:** `components/dialogs.py` y sus pruebas.
- **No incluye:** Migración de diálogos (ya hecha).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- Orden de botones oficial: ¿acción principal a la derecha (Windows) o a la izquierda? A la derecha
