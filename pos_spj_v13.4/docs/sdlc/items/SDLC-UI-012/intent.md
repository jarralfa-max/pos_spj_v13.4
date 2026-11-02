# SDLC-UI-012 — AppSidebar: sin Inicio ni Reportes, orden distinto al estándar, encabezado crudo 'operacion' y búsqueda que coincide con todo

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §12 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
El menú lateral tiene logo, toggle y búsqueda, pero no tiene «Inicio» ni «Reportes» y no sigue el orden del documento (Configuración no va al final). Todos los módulos están en un grupo llamado `operacion`, que se imprime crudo como encabezado. La búsqueda también compara contra ese grupo, así que escribir «o» u «ope» muestra todos los módulos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/shell/sidebar/global_sidebar.py:44-48,102,148`
- `frontend/desktop/shell/sidebar/sidebar_search.py:24`
- `migrated_modules_navigation.py:127-235` (orden y grupo actuales)
- `tests/ui/shell/test_global_sidebar.py`; `tests/integration/shell/test_migrated_modules_sidebar.py`

## Impacto
Todos los usuarios: menú con un encabezado técnico visible y una búsqueda que no filtra.

## Objetivo
- La búsqueda solo compara contra el nombre del módulo y sus sinónimos
- Grupos con nombre legible, o sin encabezado
- Orden e ítems Inicio/Reportes según la decisión del responsable

## Alcance
- **Incluye:** Sidebar global y registro de navegación.
- **No incluye:** Construir una pantalla de Inicio, si no existe (va como ítem aparte si se decide).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- ¿Qué es «Inicio» (un tablero nuevo, BI, o el POS)? DASHBOAR, BI resumido y accesos rapidos ¿«Reportes» es Inteligencia de Negocios? Si
- ¿Orden oficial del menú, o el orden de §12 tal cual?
1. Inicio
-Dashboard
2. Ventas y clientes 
- POS
-CRM
- Repartos
-Whatsap
3. Abastecimiento y Distribucion 
- Compras
- Transferencias
- logistica 
4. Inventarios y Produccion
- inventario
- productos
- precios
- produccion 
- merma 
5. Administracion 
- Activos
- Finanzas 
- RRHH
- BI
6. Sistema 
- Configuracion 


