# SDLC-ARQ-SHIFT-002 — Gerente no puede consultar el turno abierto por el cajero: el contexto de Caja se filtra por usuario

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §8 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R8.1 Gerente consulta el mismo turno desde otra terminal, estado `ausente`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-SHIFT-001

## Problema
El documento pide que un gerente autorizado consulte, desde otra terminal, la misma caja y el mismo turno abierto por el cajero sin abrir otro. Con la misma base, el espacio de trabajo de Caja filtra el turno activo por el usuario conectado, así que el gerente ve 'Sin turno activo'; sólo la lista de turnos (`list_recent`) muestra el turno ajeno. Entre terminales no es posible (cada una tiene su SQLite; ver SDLC-ARQ-HYB-001).

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/desktop/cash_operational_context.py:47-65,122-132` (filtrado por usuario)
- `backend/application/cash_register/shift_query_service.py:40-89` (`list_recent` con `CAJA.turno.ver` sí lista turnos de la sucursal)
- `frontend/desktop/modules/cash_register/cash_shifts_page.py:98-99`
- Pruebas: `tests/integration/cash_register/test_cash_audit_968e0bc.py:138-168` (intervención con motivo, misma base); para §15 T6 (terminal A abre, terminal B consulta): ninguna.

## Impacto
Supervisores y gerentes no pueden revisar en vivo la caja de un cajero sin usar su sesión, lo que empuja a compartir credenciales.

## Objetivo
- Un usuario con `CAJA.turno.ver` en el ámbito ve el turno abierto de cualquier caja de su sucursal en modo consulta.
- Consultar no concede operar: las acciones siguen requiriendo sus permisos o el flujo de intervención existente.
- Prueba de integración: el cajero abre turno; el gerente consulta el mismo `shift_id` sin crear turno.

## Alcance
- **Incluye:** Modo consulta del turno ajeno en la misma base; prueba de aceptación §15 T6 en su variante de una base.
- **No incluye:** Consulta desde otra terminal (requiere SDLC-ARQ-HYB-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Auditoría de caja 968e0bc (intervención de supervisor).

## Preguntas abiertas
- Ninguna por ahora.
