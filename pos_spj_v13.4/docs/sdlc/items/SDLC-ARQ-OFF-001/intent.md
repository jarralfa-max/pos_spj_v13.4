# SDLC-ARQ-OFF-001 — No hay modelo de autorización offline: login siempre local, sin vigencia ni autoridad central

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §11 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R11.1 / R11.2 Login y autorización offline, estado `ausente`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-SYNC-003, SDLC-ARQ-TERM-001

## Problema
El login siempre valida contra `usuarios` de la SQLite local; el central aún no tiene usuarios ('Fase 6'). No hay almacén de permisos en caché con vigencia limitada ni lista de operaciones permitidas offline, ni tratamiento de revocación mientras la terminal está desconectada, pérdida de dispositivo u operaciones de alto riesgo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sync/device_provisioning.py:18-20`
- `backend/domain/offline/policies/offline_read_policy.py` (sólo frescura de lectura)
- Pruebas: ninguna (§15 T11).

## Impacto
Los privilegios locales son indefinidos; una baja de empleado no se refleja en sucursales desconectadas.

## Objetivo
- Política aprobada de vigencia offline por tipo de operación.
- Credenciales/permisos offline guardados de forma segura con expiración; al reconectar se revalida sin reatribuir operaciones.
- Prueba §15 T11.

## Alcance
- **Incluye:** Política + implementación del primer slice.
- **No incluye:** Sincronización de bajada (ARQ-SYNC-003, prerequisito).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- ¿Cuánto tiempo puede operar offline un usuario sin revalidar (horas, días)?
- ¿Qué operaciones de alto riesgo se bloquean offline (cancelaciones, devoluciones, retiros, crédito)?
