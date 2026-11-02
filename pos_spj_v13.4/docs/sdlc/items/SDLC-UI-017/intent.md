# SDLC-UI-017 — ModuleSidebar: deep-links que dejan oculta la página en grupos colapsados; badge y permiso por grupo sin uso; módulos grandes planos

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §14, §15, §16 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
Cinco módulos navegan a una página con `setCurrentRow` en vez de `select()`. Si el grupo está colapsado, la página cambia pero su fila queda oculta. El badge por grupo existe y nadie lo usa, y no hay permiso a nivel de grupo. Inventario, Productos, Configuración, Precios, BI, Mermas, Cárnico, Pedidos, Transferencias y Logística tienen sidebar plano aunque son grandes. Tampoco se recuerda la página dentro del módulo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/components/side_nav.py:93-100,117-126,166,172-185,221`
- `frontend/desktop/modules/finance/finance_view.py:167`; `hr/hr_view.py:106`; `purchasing/purchasing_module_shell.py:193`; `customers_crm/customers_crm_workspace.py:371`; `fidelidad/fidelidad_workspace.py:166` (`setCurrentRow`)
- `frontend/desktop/shell/application_shell/application_window.py:159-164`; `app.py:508-509` (se restaura el módulo, no la página)
- Finanzas tiene «Activos fijos» y existe además el módulo global «Activos»

## Impacto
Usuarios que llegan por un enlace o una notificación y no ven dónde están.

## Objetivo
- Todo deep-link pasa por `select()` (o la API que expanda el grupo) y una guardia lo exige
- Agrupación en los módulos grandes que el responsable indique
- Badge y permiso por grupo usados donde aplique, o retirados del contrato

## Alcance
- **Incluye:** `side_nav.py`, las 5 llamadas, agrupación de módulos acordados.
- **No incluye:** Rediseño de contenido de módulos.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- ¿Qué módulos planos deben agruparse primero?
- Finanzas → «Activos fijos» y el módulo «Activos»: ¿se consolida en uno? (ver SDLC-ASSET-001) Finanzas y activos son modulos separados 
- ¿Se debe restaurar la última página dentro del módulo al reabrir?
