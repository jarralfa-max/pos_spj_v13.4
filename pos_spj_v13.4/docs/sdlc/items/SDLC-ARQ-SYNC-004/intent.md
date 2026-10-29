# SDLC-ARQ-SYNC-004 — El central no aplica versión mínima ni compatibilidad de protocolo de las estaciones

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §10 · §13 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R10.5 / R13.6 Compatibilidad de versiones, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-TERM-001

## Problema
`app_version` sólo se registra; existe `SUPPORTED_ENVELOPE_VERSIONS={1}` sin negociación ni ventana N-1. Una sucursal offline que se actualice tarde no tiene garantía de compatibilidad ni el central puede rechazarla con motivo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/api/routers/devices.py:109,129`
- `backend/shared/sync/replication_envelope.py:45-46`
- `backend/api/central_app.py:29` (`API_VERSION="0.1.0"`)

## Impacto
Riesgo de incompatibilidad al desplegar por oleadas.

## Objetivo
- Política de versiones mínimas y ventana de compatibilidad publicada por el central y aplicada en sync.
- Rechazo explicado a estaciones fuera de ventana; prueba.

## Alcance
- **Incluye:** Política y verificación.
- **No incluye:** Actualizador (SDLC-INST-*).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- ¿Cuántas versiones atrás debe aceptar el central (N-1, N-2)?
