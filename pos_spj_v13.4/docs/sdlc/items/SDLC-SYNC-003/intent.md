# SDLC-SYNC-003 — Proyección central: errores permanentes, eventos fuera de orden y última-escritura-gana en crédito/lealtad

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-SYNC-001

## Problema
La proyección central salta cualquier hecho que ya tenga fila de log, incluido ERROR, y no hay forma de reintentarlo. Una reversa que llega antes que su original lanza error y nunca se proyecta; `set_sale_status` y `close_cash_shift` son UPDATE que tocan 0 filas si llegan primero y aun así se registran OK. `upsert_credit_account` y `upsert_loyalty_transaction` sobrescriben con el último proyectado sin guardia de versión; `advance_head` puede retroceder `last_version`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/central/projection_repository.py:35-37,76-78,117-120,177-207` (comparar `:223` `upsert_org_unit` con guardia)
- `backend/application/sync/central_projection.py:162-163`
- `backend/infrastructure/central/sync_inbox_repository.py:248-257`
- `scripts/central_stations.py project` sin opción de reintento

## Impacto
Consolidado central con ventas/turnos/crédito/puntos incorrectos o faltantes.

## Objetivo
- Hechos en ERROR o dependientes de un hecho faltante quedan reintentables y se proyectan cuando llega su dependencia.
- Un UPDATE que afecta 0 filas no se registra como OK.
- Proyecciones de crédito y lealtad respetan versión/orden del agregado.

## Alcance
- **Incluye:** Repositorio y servicio de proyección central, script de reintento.
- **No incluye:** Ingesta (SYNC-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Pipeline híbrido Slice 6.

## Preguntas abiertas
- Ninguna por ahora.
