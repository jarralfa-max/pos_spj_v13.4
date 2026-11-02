# SDLC-UI-028 — QSS con variantes de botón no oficiales y KPICard que solo muestra la frescura en estado STALE

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §37, §38 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
La fábrica de botones limita las variantes a las cinco oficiales, pero el QSS todavía emite success, warning, accent y outline, define `ghost` dos veces y no tiene regla para el botón de icono. `KPICard` solo muestra la frescura del dato cuando está en STALE.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/components/buttons.py:18`
- `frontend/desktop/themes/qss_builder.py:158,168-184,240-285` (`ghost` en `:170` y `:268`)
- `frontend/desktop/components/kpi_card.py:74`

## Impacto
Menor: estilos muertos y KPIs sin la hora del dato.

## Objetivo
- El QSS solo tiene las cinco variantes oficiales, cada una con sus estados
- `KPICard` muestra la frescura siempre que se le pase

## Alcance
- **Incluye:** `qss_builder.py`, `kpi_card.py`.
- **No incluye:** —

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
