# SDLC-ARQ-SYNC-002 — Conflictos centrales nunca se resuelven y hay tres modelos de conflicto paralelos

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §10 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R10.2 / R10.4 Conflictos visibles y resueltos, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-SYNC-001

## Problema
`sync_conflicts` tiene estados OPEN/RESOLVED, pero ningún código lo pasa a RESOLVED y no hay endpoint ni CLI (`scripts/central_stations.py` sólo migra, proyecta, registra y suspende). Clientes, CRM y activos tienen sus propias entidades y casos de uso de conflicto de sync, desconectados del motor de replicación y del central.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `migrations/pg/p001_central_replication.py:92-98`
- `scripts/central_stations.py:32`
- `backend/domain/{customers,crm,assets}/entities/*sync_conflict*.py`; `backend/application/{customers,crm}/use_cases/sync_conflict_use_cases.py`
- Pruebas: ninguna para resolución central.

## Impacto
Los conflictos se acumulan sin dueño; cada módulo resuelve a su manera.

## Objetivo
- Flujo de resolución determinista y auditado (quién, regla, resultado) en el central.
- Un solo modelo de conflicto; los de clientes/CRM/activos se conectan o retiran.

## Alcance
- **Incluye:** Resolución central + unificación.
- **No incluye:** Detección (ARQ-SYNC-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SYNC-002 (pregunta: quién resuelve).

## Preguntas abiertas
- Ninguna por ahora.
