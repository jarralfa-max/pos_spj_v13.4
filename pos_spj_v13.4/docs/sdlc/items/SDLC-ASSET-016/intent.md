# SDLC-ASSET-016 — Mantenimiento: planes y órdenes de trabajo sin persistencia, casos de uso ni folio; faltan ejecución, tareas y recursos

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §22–§28, §66 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** SDLC-ASSET-011, SDLC-ASSET-008

## Problema
El legacy registraba mantenimientos preventivos y correctivos, internos y externos; esa capacidad se perdió. Hoy plan y orden de trabajo existen solo como entidades, sin Execution, Task ni Resource, sin folio de OT, sin casos de uso y sin tablas. La criticidad del activo no influye en la prioridad. El proveedor externo no se busca en Compras.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/entities/maintenance_plan.py:29`, `maintenance_work_order.py:45`
- `maintenance_work_order.py:77-78` — folio lo pasa el llamador
- `backend/domain/assets/integration_ports.py:31` — `SupplierLookupPort` sin adaptador
- `backend/application/procurement/queries/supplier_directory_query_service.py:22` — consulta de Compras disponible
- `backend/application/use_cases/schedule_maintenance_use_case.py:9`, `complete_maintenance_use_case.py:9` — andamiaje `not_implemented`

## Impacto
No se puede registrar ni un mantenimiento: funcionalidad operativa perdida.

## Objetivo
- Tablas y casos de uso de §66 (crear/editar plan, OT correctiva, aprobar, asignar, iniciar, pausar, completar, cerrar, cancelar), idempotentes y con folio.
- Proveedor externo por el lookup de Compras; técnico interno por RRHH.
- Pruebas de integración del ciclo de una OT.

## Alcance
- **Incluye:** Planes y OT, folio, lookups.
- **No incluye:** Generación automática (SDLC-ASSET-017), UI de tablero (SDLC-ASSET-018), costos a Finanzas (SDLC-ASSET-019), refacciones (SDLC-ASSET-020).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- ASSET-6

## Preguntas abiertas
- ¿Mantenimiento de equipos de Procesamiento Cárnico se migra a este modelo? (ver SDLC-ASSET-034)
