# SDLC-ARQ-IDEM-003 — Guardar una venta borra y reinserta sus hijos; pagos revertidos siguen CONFIRMED

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §12 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R12.4 Nunca borrar trazabilidad, estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`SqliteSaleRepository.save` hace DELETE + INSERT de líneas, pagos, cupones, devoluciones y solicitudes de factura en cada guardado. No hay disparadores que hagan append-only `cash_ledger_entries` ni `sale_returns` (sólo existen para tablas legacy). `payment_records` nunca pasa a `REVERSED` cuando la venta se revierte y no tiene UNIQUE por `sale_id`. El documento exige no borrar trazabilidad y compensar.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/db/repositories/sales/sale_repository.py:108,128,151,158,174`
- `migrations/standalone/029_reversals_hardening.py` (disparadores sólo legacy)
- `backend/infrastructure/db/repositories/cash_register/repositories.py:248-260` (sólo escribe CONFIRMED; no hay `UPDATE payment_records`)
- `backend/application/cash_register/sales_integration.py:159` (dedup sólo en aplicación)
- Pruebas: `tests/test_phase10_sales_reversal_events.py`, `tests/integration/cash_register/test_cash_ledger_flow.py:147`.

## Impacto
Finanzas y auditoría: un error a mitad de guardado puede perder renglones; los reportes de pagos cuentan como confirmados pagos ya revertidos.

## Objetivo
- Los hijos de venta se insertan/actualizan por diferencia; nunca se borran filas confirmadas.
- Disparadores append-only en ledger de caja y devoluciones (con migración y prueba).
- `payment_records` refleja la reversa y tiene unicidad por venta.

## Alcance
- **Incluye:** Repositorio de ventas, migraciones de disparadores y unicidad, pruebas.
- **No incluye:** Bloqueo optimista (IDEM-004).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SALES-005 (modelo legacy de ventas).

## Preguntas abiertas
- Ninguna por ahora.
