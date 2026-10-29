# SDLC-ARQ-SYNC-003 — No existe sincronización de bajada (central → estación): maestros, precios, permisos y revocaciones

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §10 · §11 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R10.2 / R11.2 Datos y revocaciones desde el central, estado `ausente`)
- **Estado:** borrador
- **Depende de:** SDLC-SYNC-005, SDLC-ARQ-TERM-004

## Problema
La sincronización es sólo de subida. No hay endpoint ni cliente para bajar catálogos, precios, usuarios, permisos, asignaciones ni revocaciones de terminal. Sin esto no puede implementarse la autorización de actor en el central (SDLC-SEC-003 depende del 'Slice 7') ni la política de permisos offline.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/api/routers/sync.py:31` (sólo `/api/v1/sync/events` de entrada)
- `backend/application/sync/central_ingestion.py:88-95` (docstring: catálogo central 'Slice 7' pendiente, *verificado directamente*)
- Pruebas: ninguna.

## Impacto
Cada sucursal mantiene maestros y permisos por separado; una revocación central nunca llega.

## Objetivo
- Protocolo versionado de bajada con cursor por estación, idempotente.
- Primer slice: usuarios, asignaciones y permisos efectivos + estado de terminal.
- Pruebas de integración estación↔central.

## Alcance
- **Incluye:** Protocolo y primer slice.
- **No incluye:** Maestros de producto/precios (slices posteriores).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SEC-003.

## Preguntas abiertas
- Ninguna por ahora.
