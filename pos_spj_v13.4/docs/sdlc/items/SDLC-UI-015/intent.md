# SDLC-UI-015 — Contador de notificaciones calculado sobre 50 filas y avisos que no llevan a su origen

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §23 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
El badge cuenta los no leídos dentro de las 50 notificaciones más recientes, no con `unread_count`, así que con más de 50 sin leer el número se queda corto. Abrir un aviso lo marca como leído, pero no lleva a la pantalla de origen. El refresco es cada 60 segundos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/shell/application_shell/notification_inbox_feed.py:51-58,60`
- `backend/application/notifications/user_inbox_service.py:16,27,36` (`INBOX_PAGE_SIZE=50`; `unread_count` sin uso en el shell)
- `frontend/desktop/shell/application_shell/notification_drawer.py:102,141-144`
- `frontend/desktop/shell/desktop_shell_window_composition.py:183,269-271` (60 s)
- `tests/ui/shell/test_notification_inbox_feed.py`; `test_notification_drawer.py`

## Impacto
Gerentes con muchos avisos ven un conteo falso y tienen que buscar a mano la pantalla de cada aviso.

## Objetivo
- El badge usa `unread_count`
- Un aviso con destino navega a su ruta, respetando permisos

## Alcance
- **Incluye:** Feed, drawer y centro de notificaciones.
- **No incluye:** Push en tiempo real.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
