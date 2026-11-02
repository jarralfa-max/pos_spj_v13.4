# SDLC-UI-007 — Densidad global por usuario de Windows: POS, Inventario, Recepción y Producción no arrancan en TOUCH

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §10 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
Los tres perfiles existen con los tamaños correctos, pero la densidad es una sola para toda la app, se guarda por usuario de Windows y no por terminal, y su valor por defecto es `comfortable`. `POSPage` declara `touch` pero nadie lee esa propiedad, así que ninguna pantalla táctil arranca en TOUCH. Los perfiles de densidad que se administran en Configuración no se aplican.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/themes/tokens.py:25-29` (valores dentro del rango del documento)
- `frontend/desktop/themes/theme_manager.py:46,75-84` (`comfortable` por defecto; `QSettings` `appearance/density`)
- `frontend/desktop/components/pages.py:104` (`POSPage` → `density='touch'` sin selector QSS)
- Adopción de `POSPage`: 0 archivos en `frontend/desktop/modules`
- `frontend/desktop/modules/configuracion/configuracion_presenter.py:291-293,859` (perfiles en la base sin conectar)

## Impacto
Cajeros y personal de almacén y producción en pantallas táctiles con controles de 42 px en vez de 52 px.

## Objetivo
- La densidad puede fijarse por terminal
- Las pantallas operativas que el responsable defina usan TOUCH por defecto, sin afectar a las administrativas
- Una prueba verifica la altura de controles del POS en la terminal táctil

## Alcance
- **Incluye:** `ThemeManager`, `POSPage` o un mecanismo equivalente por pantalla, POS y las pantallas operativas que se acuerden.
- **No incluye:** Perfiles de densidad en la base (SDLC-SET-003).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- ¿La densidad TOUCH va por terminal (todo táctil en esa PC) o por pantalla (solo POS, recepción, producción e inventario operativo)? Por terminal
- ¿Qué pantallas exactas de Inventario, Recepción y Producción son «operación táctil»? todas
