# SDLC-UI-024 — RRHH: 32 QLineEdit y 8 QDateEdit nativos

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/ui-ux.md` §39, §46.23 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-ui-ux.md`)
- **Estado:** aprobado (2026-10-31, Alfred)
- **Depende de:** SDLC-UI-011

## Problema
Los formularios de RRHH usan inputs nativos en lugar de los especializados (teléfono, email, fecha, dinero) y de `FormField`, así que no tienen estado de error, ayuda ni teclado virtual.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura (2026-10-29); las marcadas *medido* salen de comandos ejecutados en esta sesión. Lo no comprobado se marca **no verificado**.

- Conteo del barrido: `QLineEdit` 32 y `QDateEdit` 8 en `frontend/desktop/modules/hr/` (archivos exactos: **no verificado**, a medir en Design)

## Impacto
Altas de empleado sin validación visual consistente.

## Objetivo
- 0 inputs nativos en `modules/hr`; cada campo usa su input especializado dentro de `FormField`

## Alcance
- **Incluye:** `frontend/desktop/modules/hr/`.
- **No incluye:** Reglas de nómina.

## Restricciones
`docs/sdlc/inputs/ui-ux.md` §47: no crear un componente visual sin comprobar antes que no exista uno estándar equivalente (`frontend/desktop/design_system/component_contracts.py`); dirección Design System → Shell → Layouts → Componentes → Módulos. CLAUDE.md regla 7 y 13 (UI sin SQL ni reglas de negocio); `docs/skills/SPJ_REFACTOR_SKILL.md` (rutas dentro de `pos_spj_v13.4/`, UUIDv7 si se crean identificadores). No ampliar `tests/architecture/design_system_debt_baseline.json` para aceptar deuda nueva (política del propio archivo). Pruebas Qt con `QT_QPA_PLATFORM=offscreen`; presupuesto $0; Windows 10/11. Nivel T2: plan corto y pruebas afectadas (`tests/ui` + guardias de `tests/architecture` del Design System).

## Trabajo previo relacionado
Pipeline del documento trabajado desde 2026-09-12 (`docs/refactor/*_phase_N.md`, fases 1-10 y parte de la 13; el responsable pidió no fiarse de esos reportes sino del código). MessageDialog reemplazó 445 `QMessageBox` el 2026-10-28.

## Preguntas abiertas
—
