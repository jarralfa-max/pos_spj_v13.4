# SDLC-UI-005 — Segundo sistema visual: webs de delivery/logística con paleta azul propia y PDF de BI con colores sueltos

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §3 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
El documento prohíbe mantener dos sistemas visuales. Las apps web de delivery y logística definen su propia paleta azul marino (cerca de 60 hex), ajena a JUANIS, y el PDF exportado de BI usa colores escritos a mano.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/web/delivery/styles.css`, `frontend/web/logistics/styles.css` (`--navy:#123c69`, `--blue:#2877b7`…)
- `backend/application/analytics/services/bi_export_service.py:157,161` (`#1E3A5F`, `#CCCCCC`)
- `backend/infrastructure/printing/ticket_template.py:59-65`: CSS térmico monocromo (aceptable, no es brecha)
- Pruebas: ninguna cubre `frontend/web`

## Impacto
Repartidores y personal de logística ven otra marca; los reportes no llevan la identidad JUANIS.

## Objetivo
- Las webs y el PDF consumen tokens generados desde la misma fuente que el QSS (por ejemplo, variables CSS exportadas desde `semantic_colors.py`)
- Una prueba falla si aparece un hex fuera de esa fuente en `frontend/web`

## Alcance
- **Incluye:** CSS de `frontend/web/*`, colores del PDF de BI.
- **No incluye:** Rediseño de las webs.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- ¿Las PWA de delivery y logística deben llevar identidad JUANIS, o se aceptan como producto aparte? Identidada JUANIS
