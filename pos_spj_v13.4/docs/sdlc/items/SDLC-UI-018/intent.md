# SDLC-UI-018 — CRM tiene pestañas dentro de pestañas (4 niveles) y un componente de pestañas propio (PillTabBar)

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §18, §19 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
El documento prohíbe pasar de 3 niveles de navegación y pide un solo TabBar canónico. El expediente del cliente tiene 12 pestañas, y su pestaña «Comercial» contiene otra barra de pestañas: son 4 niveles. CRM usa además su propio `PillTabBar` en 4 pantallas.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/customers_crm/pages/customer_profile_page.py:146,318,438,458`
- `frontend/desktop/modules/customers_crm/pages/_pill_tab_bar.py:28`; usos en `opportunity_pages.py:373`, `_work_items.py:126`
- `frontend/desktop/components/tabs.py:9,28` (canónico); `tests/architecture/test_design_system_guardrails.py:124` (no detecta `PillTabBar`)

## Impacto
Usuarios de CRM: navegación profunda y con dos estilos de pestaña.

## Objetivo
- Expediente con máximo 3 niveles
- `PillTabBar` reemplazado por `Tabs`/`TabBar`, o incorporado al catálogo canónico si aporta algo que el canónico no tiene
- La guardia detecta pestañas anidadas y componentes de pestañas locales

## Alcance
- **Incluye:** Páginas de CRM listadas y la guardia.
- **No incluye:** Rediseño funcional del expediente.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Memoria del proyecto: «Menú no repite el expediente» (nada en el menú lateral que ya sea pestaña del expediente).

## Preguntas abiertas
- ¿Qué contenido de la pestaña «Comercial» pasa a nivel 3 y qué sale del expediente? Segun logica de negocio 
