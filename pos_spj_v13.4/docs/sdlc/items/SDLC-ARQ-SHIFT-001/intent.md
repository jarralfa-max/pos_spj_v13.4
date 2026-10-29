# SDLC-ARQ-SHIFT-001 — Turno activo resuelto por ~12 caminos distintos: Caja y POS discrepan sobre si hay turno

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §8 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R8.2 Fuente canónica del turno activo, estado `duplicado`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El documento exige una única fuente canónica del turno activo. Hoy la tabla es una sola (`cash_shifts`), pero el *turno activo* se resuelve por unos doce caminos con filtros y conjuntos de estado distintos: sólo `OPEN` y filtrado por sucursal+cajero (ventas, devoluciones, efectos de caja), `ACTIVE_STATUSES` sin filtro de sucursal (apertura), por recurso, una caché en memoria en `composition_root.active_cash_shift_id`, el renglón seleccionado en pantalla y tuplas de estado copiadas a mano en vista general, cierre financiero, actualizaciones y organización. Resultado observable: con un turno `SUSPENDED` Caja lo muestra como activo y el POS responde "no tienes turno abierto"; un gerente ve "Sin turno activo" aunque el cajero tenga uno abierto.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/db/repositories/cash_register/repositories.py:63` `find_open_for_cashier` (sólo `OPEN`, sucursal+cajero) — usado en `backend/application/cash_register/sales_integration.py:93,155`, `refund_integration.py:107`, `backend/infrastructure/integrations/sales_cash_effects_client.py:57`
- `repositories.py:72` `find_active_for_cashier` (`ACTIVE_STATUSES`, sin sucursal) — `backend/application/cash_register/shift_use_cases.py:69`; `repositories.py:82` `find_active_for_resource` — `shift_use_cases.py:72-78`
- `backend/infrastructure/desktop/cash_operational_context.py:47-65,116-152,193-229` (caché en memoria + fallback a cualquier turno del usuario); escrituras de la caché en `:63,:137` y `backend/infrastructure/desktop/cash_register_factory.py:548`
- `frontend/desktop/modules/cash_register/cash_register_presenter.py:99-106`, `cash_shifts_page.py:98`, `cash_register_workspace.py:206` (la UI decide qué turno usar)
- Estados copiados: `backend/application/cash_register/overview_query_service.py:163,220` (`OPEN/SUSPENDED/CLOSING`), `backend/infrastructure/integrations/finance_close_sources.py:15,66`, `backend/infrastructure/db/repositories/software_updates/station_update_repository.py:130,162`, `backend/infrastructure/db/repositories/organization/org_unit_repository.py:148`; canónico en `backend/domain/cash_register/policies/workflow_policies.py:21-30`
- Tres copias de "¿tienes turno?" en POS: `frontend/desktop/modules/sales_pos/composition.py:128-140`, `backend/application/sales/use_cases/checkout_use_cases.py:202-210`, `return_use_cases.py:177-182`
- Ninguna prueba compara las fuentes entre sí (existentes: `tests/architecture/test_cash_operational_context_resolver.py`, `tests/integration/cash_register/test_cash_register_factory_active_context.py:94`).

## Impacto
Cajero, supervisor y gerente. Ventas o devoluciones pueden asociarse a un turno distinto del que Caja muestra, o rechazarse con turno abierto; el corte Z y el cierre financiero pueden leer un conjunto de turnos distinto al operativo. Riesgo de dinero (efectivo atribuido al turno equivocado) y bloqueo operativo.

## Objetivo
- Existe un único servicio de aplicación `ActiveShiftResolver` (o equivalente) con una sola definición de estados activos tomada de la política de dominio.
- Todos los consumidores listados en la evidencia lo usan; no queda caché en `composition_root` ni tuplas de estado copiadas.
- Una prueba de arquitectura impide nuevas consultas de turno activo fuera del resolvedor.
- Una prueba de integración demuestra que Caja, POS, devoluciones y cierre financiero devuelven el mismo turno para los estados OPEN, SUSPENDED y CLOSING.

## Alcance
- **Incluye:** Resolvedor canónico, migración de consumidores, guardia de arquitectura, pruebas de coherencia.
- **No incluye:** Consulta del turno por un gerente (SDLC-ARQ-SHIFT-002), concurrencia (SDLC-ARQ-SHIFT-004), coordinación entre terminales (SDLC-ARQ-HYB-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SALES-007 (POS reporta cualquier `OperationalError` como 'no hay turno abierto') toca `sales_pos/composition.py:134-138`: conviene hacerlo dentro de este ítem o justo después. SDLC-CASH-001 (reversa en turno cerrado) depende de esta resolución.

## Preguntas abiertas
- ¿Un turno `SUSPENDED` cuenta como activo para vender? ¿Y `CLOSING`? (hoy cada consumidor responde distinto)
