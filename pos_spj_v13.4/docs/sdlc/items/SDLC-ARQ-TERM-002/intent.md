# SDLC-ARQ-TERM-002 — Re-anclar la sucursal de la estación no tiene autorización en backend, ni auditoría, ni candado

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §5 · §6 · §14 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R5.4 / R6.5 / R14.2 Sucursal de la terminal no alterable, estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El documento prohíbe que una terminal altere su sucursal sin autorización y que el login cambie la sucursal en silencio. `SetInstallationBranchUseCase` no verifica permiso (sólo el presentador comprueba `CONFIGURACION.empresa.editar`), no audita, no revisa turno abierto ni sync pendiente y no consulta el registro central. El ancla es una fila plana en `configuraciones`, editable en el archivo SQLite sin que nadie lo note. Si falta el ancla, la sesión usa en silencio la sucursal del usuario.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/use_cases/set_installation_branch_use_case.py:22-28` (*verificado directamente*)
- `frontend/desktop/modules/configuracion/configuracion_presenter.py:1179-1198`
- `backend/infrastructure/db/repositories/settings/installation_branch_repository.py:48-69`
- `backend/bootstrap/application_context_builder.py:123-129` (fallback a sucursal propia, *verificado directamente*)
- Pruebas: `tests/unit/test_empresa_page_installation_branch.py:106-125` (UI); `tests/test_installation_branch_resolution.py` importa `core.services.branch_resolution`, que ya no existe.

## Impacto
Un usuario con permiso de editar empresa (o cualquiera con acceso al archivo) puede mover una caja a otra sucursal con turno abierto y ventas sin sincronizar: ventas, efectivo e inventario quedan en la sucursal equivocada.

## Objetivo
- El caso de uso exige un permiso específico de re-anclaje verificado en backend.
- Se rechaza con turno abierto o eventos pendientes de sincronizar, con motivo explicado.
- El cambio se audita (actor, terminal, sucursal anterior y nueva, operation_id).
- Sin ancla, la estación no inicia sesión operativa (no hay fallback silencioso) salvo el flujo de provisión.
- Prueba de integración para cada regla.

## Alcance
- **Incluye:** Caso de uso, repositorio, builder de contexto, pruebas.
- **No incluye:** Propagar el cambio a la sesión viva (SDLC-SET-001), protección criptográfica del ancla (TERM-005).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SET-001 (el cambio no llega a la sesión en curso) — mismo archivo de UI; puede hacerse en la misma rama si el responsable lo aprueba.

## Preguntas abiertas
- ¿Re-anclar requiere además aprobación central (cuando haya registro central) o basta un permiso local?
