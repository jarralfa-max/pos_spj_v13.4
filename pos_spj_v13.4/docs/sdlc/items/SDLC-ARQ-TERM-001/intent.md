# SDLC-ARQ-TERM-001 — Identidad de terminal fragmentada en cinco lugares; la sesión usa el hostname

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §5 · §6 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R5.3 Registro de terminal, estado `duplicado`)
- **Estado:** borrador
- **Depende de:** SDLC-SYNC-001

## Problema
El documento pide que cada terminal registrada tenga `terminal_id` único y persistente, tipo, ámbito, estado, versión de app, de esquema y de protocolo. Hoy la terminal existe en `workstations`, `pos_terminals` (no ligada a la máquina física), `device_enrollment` (354, sin registrar ni usar), `software_station_settings` (por **hostname**) y en el central (`sync_stations`/`replication_stations`). La sesión de escritorio se construye sin `workstation_id` y cae al hostname; `LegacySessionAdapter.workstation_id` es `None` en producción; `sales.workstation_id` es nullable. Renombrar el equipo cambia la estación.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/app.py:518`; `frontend/desktop/shell/desktop_shell_authentication_composition.py:79` (default `""`)
- `backend/bootstrap/application_context_builder.py:112`; `backend/bootstrap/application_context.py:43-47,279-283`
- `backend/bootstrap/legacy_session_adapter.py:125-128`
- `backend/infrastructure/db/schema/settings_schema.py:172-195` (`workstations`)
- `migrations/standalone/175_cash_register_bounded_context_schema.py:8-22` (`pos_terminals`)
- `backend/infrastructure/desktop/software_updates_factory.py:70` (hostname)
- `migrations/pg/p001_central_replication.py:28-40`, `p006_device_provisioning.py:24-35`
- `backend/infrastructure/db/schema/sales_schema.py:67-68`
- Pruebas: ninguna para el registro de terminal.

## Impacto
Sin identidad estable no se puede: validar la terminal al login, ligar POS a caja/cajón, auditar por terminal, revocar un equipo ni sincronizar con autoridad. Bloquea la operación multi-terminal.

## Objetivo
- Una sola entidad canónica de terminal con `terminal_id` UUIDv7 persistente (no hostname), tipo, ámbito, estado y versiones (app, esquema, protocolo).
- La sesión, ventas, caja y auditoría usan ese id.
- `pos_terminals` y los demás registros quedan como vista/derivado o se retiran con migración sin pérdida.
- Prueba: renombrar el host no cambia la identidad.

## Alcance
- **Incluye:** Decisión de fuente canónica, migración local, cableado en sesión.
- **No incluye:** Enrolamiento con el central (TERM-004/005), validación en login (TERM-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SYNC-001 (¿354 forma parte del slice de p006?). SDLC-CORE-004 (migraciones sin registrar).

## Preguntas abiertas
- ¿Cuál de las tablas actuales debe ser la fuente canónica de terminal (`workstations` parece la más completa)?
