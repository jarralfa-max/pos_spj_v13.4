# SDLC-ARQ-INST-002 — Respaldo de actualización omite configuración e identidad; desinstalar borra install_config.json

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §13 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R13.1 / R13.5 Conservar datos, identidad y pendientes, estado `parcial`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El respaldo previo a actualizar cubre sólo la SQLite (no `install_config.json`, `station_settings.json` ni `secrets/`). La desinstalación borra `{app}\install_config.json` (perfil, canal, hosts) y la clave `InstalledVersion`. Ninguna prueba verifica que una actualización conserve cola de sync, identidad de terminal, sucursal y permisos; el marcador de CI es una sola fila.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `installer/windows/spj_setup.iss:151-152` (*verificado directamente*), `:464`
- `scripts/release/ci_data_marker.py`
- `tests/integration/software_distribution/test_update_use_cases.py::test_open_shift_and_pending_outbox_do_not_block` (sólo que no bloquean)

## Impacto
Reinstalar o reparar puede dejar la terminal sin perfil ni identidad; restaurar no devuelve la configuración.

## Objetivo
- Respaldo de actualización incluye configuración e identidad (secretos según política de ARQ-INST-003).
- La desinstalación conserva configuración salvo opción explícita.
- Prueba §15 T12: actualización exitosa/fallida/rollback conserva cola, identidad, ancla y permisos.

## Alcance
- **Incluye:** Transacción de actualización, instalador, prueba.
- **No incluye:** Firma (SDLC-INST-001/002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-INST-003.

## Preguntas abiertas
- Ninguna por ahora.
