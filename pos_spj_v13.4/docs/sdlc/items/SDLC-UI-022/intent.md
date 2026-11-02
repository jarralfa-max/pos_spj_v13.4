# SDLC-UI-022 — La matriz de 5 resoluciones solo cubre 4 módulos y con páginas de relleno

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §9, §45.7 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-001, SDLC-UI-002

## Problema
La prueba que recorre 1280×720, 1366×768, 1440×900, 1600×900 y 1920×1080 solo cubre Caja, CRM, Fidelidad y Activos, y usa `QWidget` vacíos en lugar de las pantallas reales. No se valida responsive en Inventario, Productos, RRHH, Logística, Cárnico, Mermas, Precios, BI ni Pedidos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `tests/ui/test_route_module_layout.py:54`; fixture en `tests/ui/test_route_sidebar_icons.py:16-34`
- Parciales: `tests/unit/test_sales_pos_visual_validation.py` (1366, 1920); `tests/ui/test_module_workspace_layout.py` (1024/1366/1440)

## Impacto
No hay garantía de que botones críticos o footers sean alcanzables en 1280×720 en la mayoría de los módulos.

## Objetivo
- Una prueba parametrizada carga la pantalla principal real de cada módulo en las 5 resoluciones y verifica que las acciones principales quedan visibles o alcanzables con scroll

## Alcance
- **Incluye:** Pruebas; las correcciones que destapen van a SDLC-UI-023…026.
- **No incluye:** Comparación de imágenes (SDLC-UI-030).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
