# SDLC-UI-016 — No existe 'Cambiar sucursal': ni en Archivo ni en el menú de usuario, y el contexto no puede cambiar en sesión

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §22, §28, §33 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-SET-001, SDLC-ARQ-TERM-002, SDLC-ARQ-PERM-003

## Problema
El documento pide «Cambiar sucursal» en Archivo y en el menú de usuario, con un diálogo institucional con logo. No existe en ningún menú. `ApplicationWindow.update_context` no tiene llamador en producción, así que la sucursal de la sesión no puede cambiar sin cerrar sesión. Re-anclar la sucursal de la estación ya existe en Configuración y tiene sus propios problemas (SDLC-ARQ-TERM-002, SDLC-SET-001). El documento pide no duplicar funciones.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/shell/application_shell/top_bar.py:63-72,76-83` (Archivo: Cerrar sesión, Salir; usuario: Mi perfil, Cerrar sesión)
- `frontend/desktop/shell/application_shell/application_window.py:153` (`update_context` sin llamador)
- `frontend/desktop/modules/configuracion/pages/empresa_page.py:408-412` (anclaje de estación, SDLC-SET-001)

## Impacto
Usuarios con alcance en varias sucursales (supervisores, dueño) tienen que cerrar sesión. El cambio de sucursal cambia el alcance de permisos, así que es una operación de seguridad.

## Objetivo
- Según la decisión del responsable: o una acción «Cambiar sucursal» que cambia la sucursal operativa de la sesión, validada en backend contra el alcance del usuario, auditada y con diálogo institucional; o la entrada lleva a la función existente sin duplicarla
- El menú y los permisos se recalculan tras el cambio (ver SDLC-ARQ-SESS-001)

## Alcance
- **Incluye:** Acción en el shell, diálogo y caso de uso de cambio de sucursal de la sesión.
- **No incluye:** Re-anclar la estación (SDLC-ARQ-TERM-002).

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SET-001 (anclar la instalación no cambia la sesión), SDLC-ARQ-TERM-002 (re-anclar sin autorización en backend), SDLC-ARQ-PERM-003 (resolvedores de alcance), SDLC-ARQ-SESS-001 (menú conserva permisos del login).

**Nota de SDLC-ARQ-AUD-001 (2026-10-30):** al construir `ApplicationContextService` en producción, pasar `audit_sink=build_security_audit_sink(conn)` (`backend/infrastructure/db/repositories/security/security_audit_sink.py`). Con eso los rechazos (`APPLICATION_CONTEXT_SWITCH_DENIED`, con motivo) y los cambios (`APPLICATION_CONTEXT_CHANGED`) quedan en `audit_logs`; hoy el servicio no tiene composición y sus eventos no llegan a ningún lado. Probado en `tests/integration/bootstrap/test_context_switch_audit.py`.

## Preguntas abiertas
- «Cambiar sucursal» ¿cambia la sucursal operativa de la sesión de un usuario multi-sucursal, o re-ancla la terminal? Cambia pero se mantiene el anclaje original Si es lo segundo, ¿la entrada del menú solo lleva a Configuración?
- ¿Cambiar de sucursal exige volver a escribir la contraseña? Si, y si el usuario no tiene credenciales para esa sucursal niega el acceso
- ¿Se permite si hay un turno de caja abierto? si pero no abre otro turno
