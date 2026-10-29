# SDLC-ARQ-HYB-002 — Operación degradada sin política: nada se bloquea sin coordinación y el estado offline nunca se fija

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §9 · §11 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R9.1 / R9.3 / R11.3 Operación degradada, estado `ausente`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-HYB-001

## Problema
Ningún caso de uso de ventas o caja revisa conectividad; `SetCashSyncConnectivityUseCase` sólo detiene el transporte. La política de frescura `offline_read_policy` no tiene consumidor, `ViewState.STALE` no se usa en caja/turno, y `ApplicationContext.offline_status` queda en 'ONLINE' para siempre, así que el mensaje REQUIRES_ONLINE del router nunca aparece.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/cash_register/offline_sync.py:154-166`
- `backend/domain/offline/policies/offline_read_policy.py`
- `frontend/desktop/components/view_states.py:24`
- `backend/bootstrap/application_context.py:347`; `frontend/desktop/shell/router/desktop_router.py:166-176`
- Pruebas: `tests/unit/shell/router/test_desktop_router_offline.py` (router aislado); `tests/integration/offline/*` (sólo caché).

## Impacto
Sin internet (o sin servicio local) la terminal no indica que sus datos de otras máquinas están desactualizados ni limita operaciones que requieren coordinación.

## Objetivo
- Catálogo de operaciones: permitidas offline / limitadas / bloqueadas, aprobado.
- Detector de conectividad que alimenta `offline_status`; las vistas de caja e inventario muestran frescura.
- Procedimientos de reconexión y fallo del anfitrión documentados y probados (§15 T10).

## Alcance
- **Incluye:** Política, detector, cableado UI, pruebas.
- **No incluye:** Auth offline (OFF-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- ¿Qué operaciones se permiten sin servicio local ni internet (venta en efectivo sí, crédito no, etc.)?
