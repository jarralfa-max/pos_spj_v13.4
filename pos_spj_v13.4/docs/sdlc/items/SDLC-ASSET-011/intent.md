# SDLC-ASSET-011 — Casos de uso de registro de activos con autorización en backend, auditoría y outbox de eventos

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §64, §86, §87, §88 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** SDLC-ASSET-010, SDLC-ASSET-006, SDLC-ASSET-007

## Problema
No existe ningún caso de uso de Activos (crear, editar, comisionar, suspender, reactivar, cambiar condición). La política de autorización existe pero nadie la llama; su docstring dice «siempre auditado» y no audita. Ningún evento de Activos se publica: no hay outbox, ni dispatcher, ni suscriptores. El sobre de evento usa `timestamp` en vez de `occurred_at` y no lleva `entity_id`, a diferencia del de Finanzas. Hay un segundo catálogo de eventos de activos en `backend/shared/events/event_names.py` que tampoco usa nadie.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- No existe `backend/application/assets/use_cases/`
- `backend/application/assets/authorization.py:59-70` — `require` sin llamadores; `:7` «always audited»; `:72-83` `authorize_exception` sin auditoría
- `backend/domain/assets/events.py:19-108` — ~75 constantes sin productor; `:134-149` sobre con `timestamp`, sin `entity_id`
- `backend/shared/events/event_names.py:49-51` — `ASSET_CREATED`, `MAINTENANCE_SCHEDULED`, `MAINTENANCE_COMPLETED` sin productor
- `backend/domain/assets/repository_ports.py:235-247` — puertos de outbox y eventos procesados sin implementación
- Finanzas como referencia de sobre: `backend/application/services/finance/posting_engine.py:383-384`

## Impacto
Sin esto la UI no tiene a qué llamar y nada se audita.

## Objetivo
- Los seis casos de uso de §64, idempotentes por `operation_id`, con `require()` en backend.
- Toda mutación escribe auditoría (usuario, autorizador, operación, antes/después, motivo, sucursal, estación, correlación).
- Outbox de Activos drenado post-commit con un solo catálogo de eventos y el sobre canónico.
- Pruebas de integración con SQLite real, incluida denegación sin permiso y doble envío.

## Alcance
- **Incluye:** Casos de uso de §64, auditoría, outbox, unificación del catálogo de eventos.
- **No incluye:** Custodia, transferencias, mantenimiento, bajas (sus ítems). Consumidores en Finanzas.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- SDLC-SALES-003 (outbox sin dead-letter: no repetir el patrón)
- Memoria Cash-AUD (outbox drenado al arranque y periódico)

## Preguntas abiertas
- Ninguna por ahora.
