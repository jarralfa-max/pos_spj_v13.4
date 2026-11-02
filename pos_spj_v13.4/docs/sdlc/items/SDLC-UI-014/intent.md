# SDLC-UI-014 — Bloque de usuario sin iniciales ni rol, Acerca de sin logo y Configuración deshabilitada sin explicación

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §21, §24, §25, §28, §33 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** —

## Problema
El bloque de usuario muestra nombre y sucursal, pero no el avatar de iniciales ni el rol (el rol solo aparece en «Mi perfil», que es de solo lectura). «Acerca de» es una página de Configuración sin el logo institucional. Cuando el usuario no tiene permiso de Configuración, el botón se deshabilita sin decir por qué.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/shell/application_shell/top_bar.py:84,100-104,122`
- `frontend/desktop/shell/application_shell/application_window.py:176-181`
- `user_profile_dialog.py` (solo lectura; ruta completa **no verificada**)
- `frontend/desktop/modules/configuracion/pages/actualizaciones_page.py:90` («Acerca de»)

## Impacto
Menor: identificación del usuario y su rol en cajas compartidas.

## Objetivo
- Iniciales y rol visibles en el bloque de usuario
- «Acerca de» accesible desde el shell con logo completo (§33)
- El botón de Configuración sin permiso explica la causa con un tooltip

## Alcance
- **Incluye:** TopBar, menú de usuario, diálogo «Acerca de».
- **No incluye:** Edición de perfil y cambio de contraseña.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
- ¿«Mi perfil» debe permitir cambiar la contraseña propia o seguir de solo lectura? Cambiar
