# SDLC-ARQ-SYNC-001 — Conflictos entre estaciones invisibles: sin autoridad por entidad ni detección de turno doble o sobreventa

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §10 · §12 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R10.4 Autoridad por entidad, sin LWW, estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** SDLC-SYNC-002, SDLC-SYNC-003, SDLC-ARQ-TERM-001

## Problema
El documento prohíbe 'gana el último' para inventario, caja, turnos y contabilidad y exige autoridad definida por entidad. La detección de conflictos es por estación: `aggregate_version` es un contador local y `station_head` filtra por estación, así que dos terminales que tocan el mismo stock, turno o cliente nunca generan conflicto; `sync_aggregate_heads` se sobrescribe con la última estación. La proyección central no detecta dos turnos abiertos en la misma caja ni sobreventa entre cajas. No existe una matriz de autoridad por entidad.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/central/sync_inbox_repository.py:240-257`
- `migrations/pg/p002_aggregate_head_station.py:1-8`
- `backend/infrastructure/central/projection_repository.py:108-115` (`ON CONFLICT (shift_id) DO NOTHING`)
- `migrations/pg/p004_central_cash_finance_credit_loyalty.py:28-40` (sin unicidad por caja)
- Pruebas: `tests/unit/central_sync/test_central_ingestion.py:138,150` confirman el comportamiento por estación; entre estaciones: ninguna.

## Impacto
Con cajas autónomas (D1) dos cajas pueden vender el mismo inventario o abrir dos turnos en la misma caja y el central lo consolida sin alertar. Riesgo de inventario y efectivo duplicados.

## Objetivo
- Matriz de autoridad por entidad y tipo de operación aprobada (estación, servicio local o central).
- El central detecta y registra como conflicto visible: dos turnos abiertos por caja/cajón, existencias negativas por sobreventa entre estaciones, versiones concurrentes de agregados compartidos.
- Pruebas con dos estaciones simuladas.

## Alcance
- **Incluye:** Matriz, detección central, pruebas.
- **No incluye:** Pantalla de resolución (ARQ-SYNC-002); LWW de crédito/lealtad (SDLC-SYNC-003).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SYNC-002, SDLC-SYNC-003 (LWW en crédito/lealtad y, ampliado, en unidades organizacionales).

## Preguntas abiertas
- Autoridad del inventario: ¿la estación que vende, el servicio local o el central? (decide si la sobreventa entre cajas se previene o sólo se detecta)
