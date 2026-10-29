# SDLC-ARQ-TERM-005 — El escritorio nunca se enrola ni consulta su estado en el central; la instalación no registra la terminal

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §5 · §6 · §13 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R6.7 / R13.2 Registro seguro de terminal, estado `documentado no implementado`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-TERM-004

## Problema
No hay cliente de enrolamiento: la estación no genera llaves, no llama a `/devices`, no consulta `/devices/me` y no conecta `on_access_denied` del transporte. La tabla local `device_enrollment` (354) no tiene lector ni escritor. La instalación sólo escribe el perfil de módulos en `install_config.json`; con `/CURRENTUSER` ese archivo lo puede modificar el propio usuario.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `migrations/standalone/354_device_enrollment.py` (no está en `MIGRATIONS`)
- `backend/infrastructure/sync/http_transport.py` (sin llamadores)
- `installer/windows/spj_setup.iss:339-373`
- Pruebas: ninguna.

## Impacto
La revocación central de una terminal no tiene efecto en la sucursal; el registro seguro de terminal (§13) no existe.

## Objetivo
- Flujo de enrolamiento desde la estación (invitación → llave → registro) con identidad de TERM-001.
- La estación consulta su estado al iniciar y al sincronizar y bloquea operación productiva si está suspendida/revocada.
- Prueba de integración contra el central en memoria.

## Alcance
- **Incluye:** Cliente de enrolamiento, consulta de estado, migración 354 registrada o retirada.
- **No incluye:** Transporte de replicación periódico (SDLC-SYNC-005).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SYNC-001 pregunta abierta sobre 354.

## Preguntas abiertas
- ¿El enrolamiento se hace en la instalación (con código de invitación) o en el primer arranque por un administrador?
