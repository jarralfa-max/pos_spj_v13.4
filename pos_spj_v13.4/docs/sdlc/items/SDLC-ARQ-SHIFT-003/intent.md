# SDLC-ARQ-SHIFT-003 — Permisos de caja definidos pero nunca verificados y entrega de turno sin implementar

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §8 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R8.3 Permisos separados de caja, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-SHIFT-001

## Problema
El catálogo de caja distingue consultar, abrir, suspender, cerrar, revisar, etc., pero `CAJA.turno.cerrar` (`SHIFT_CLOSE`) y `Z_CUT_REVIEW` nunca se verifican: cerrar exige en realidad `SHIFT_PREPARE_CLOSE` + `Z_CUT_GENERATE`. `SHIFT_FORCE_CLOSE` se reutiliza como permiso genérico de 'intervenir turno ajeno' (también para movimientos) y el estado `FORCE_CLOSED` nunca se alcanza; `PENDING_REVIEW` y `COUNTED` tampoco. La tabla `cash_shift_assignments` nunca se escribe, así que no hay entrega ni reasignación de un turno vivo con trazabilidad.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/cash_register/permissions.py:34-53`
- `backend/application/cash_register/z_cut_use_cases.py:43,62`
- `backend/application/cash_register/ledger_use_cases.py:106`, `movement_use_cases.py:89`
- `migrations/standalone/175_cash_register_bounded_context_schema.py:34-41` (`cash_shift_assignments`)
- Pruebas: `tests/architecture/test_cash_register_permissions_catalog.py`, `tests/unit/cash_register/test_cash_register_role_matrix.py` (catálogo, no uso).

## Impacto
Un administrador que configura 'puede cerrar turno' o 'puede revisar Z' no obtiene el efecto esperado; quien puede intervenir un turno también puede registrar movimientos en él. Sin entrega de turno, el cambio de cajero obliga a cerrar o a operar con la sesión de otro.

## Objetivo
- Cada permiso del catálogo de caja se verifica en al menos un caso de uso o se retira con migración de asignaciones (sin perder configuración).
- Intervenir, forzar cierre y registrar movimientos ajenos son permisos distintos.
- Existe un flujo de entrega/reasignación de turno que escribe `cash_shift_assignments`, con permiso y auditoría.
- Estados inalcanzables documentados o retirados.

## Alcance
- **Incluye:** Permisos y transiciones de caja; entrega de turno.
- **No incluye:** Fuente canónica (SHIFT-001), concurrencia (SHIFT-004).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
CJA-02 (`backend/application/cash_register/shift_ownership.py`).

## Preguntas abiertas
- ¿La entrega de turno entre cajeros existe en la operación real o siempre se cierra y abre?
- ¿Revisar el corte Z es un paso obligatorio antes de cerrar?
