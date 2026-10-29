# SDLC-ARQ-IDEM-005 — Sin vocabulario común de estados de operación (borrador/pendiente/confirmada/rechazada/compensada)

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §12 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R12.3 Estados de operación, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-IDEM-002

## Problema
Cada entidad usa su propio conjunto: `payment_records` DRAFT/CONFIRMED/REVERSED/CANCELLED (sólo se escribe CONFIRMED), ventas DRAFT…REVERSED sin CHECK, ledger sin estado, replicación PENDING/RETRY/CONFLICT/DEAD. No hay forma uniforme de saber si una operación quedó rechazada o compensada.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `migrations/standalone/175_cash_register_bounded_context_schema.py:66`
- `backend/infrastructure/db/schema/sales_schema.py:65`
- `migrations/standalone/350_replication_engine.py:41-90`

## Impacto
Reportes de conciliación y la resolución de conflictos de sync no pueden razonar sobre el estado de negocio común.

## Objetivo
- Mapa documentado de cada estado local al vocabulario del documento, expuesto en los contratos de integración y de sync.
- CHECK de estados en ventas.

## Alcance
- **Incluye:** Contrato y mapeo; CHECK en ventas.
- **No incluye:** Renombrar estados existentes.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
