# SDLC-ARQ-TERM-004 — Registro central de dispositivos sin pruebas, duplicado y con actor admin no firmado

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §6 · §10 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R6.6 Registrar/suspender/revocar/reasignar terminal, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-SYNC-001, SDLC-ARQ-TERM-001

## Problema
`DeviceProvisioningService` y `routers/devices.py` (registrar, suspender, revocar, reasignar) no tienen pruebas. Coexiste con `CentralStationAdmin` (secreto compartido, sin auditoría ni motivo). El usuario administrador que actúa llega en la cabecera `X-SPJ-Actor-User`, que no forma parte de la cadena firmada Ed25519. `reassign` no revisa eventos pendientes de la estación. La tabla de p006 que usa no se aplica en el central (SDLC-SYNC-001).

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sync/device_provisioning.py:173-176,352-396`
- `backend/application/sync/station_admin.py:83-100`
- `backend/api/routers/devices.py:75,150,295,304`
- `backend/shared/security/device_signature.py:96-99` (cadena canónica sin actor)
- Pruebas: ninguna para provisioning, firma ni rutas `/devices` y `/admin`.

## Impacto
Registrar, suspender o reasignar una terminal se puede atribuir a cualquier usuario; reasignar con datos pendientes puede perderlos o mezclarlos.

## Objetivo
- Un solo servicio de administración de estaciones (se retira o delega el duplicado).
- El actor viaja firmado y se verifica contra un usuario central autorizado.
- Reasignar/revocar con pendientes exige drenarlos o un flujo explícito.
- Pruebas de unidad e integración del servicio y las rutas.

## Alcance
- **Incluye:** Servicio central, rutas, firma, pruebas.
- **No incluye:** Cliente de escritorio (TERM-005).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SEC-003 (central acepta cualquier actor en sync), SDLC-SEC-005 (nonce por proceso).

## Preguntas abiertas
- Ninguna por ahora.
