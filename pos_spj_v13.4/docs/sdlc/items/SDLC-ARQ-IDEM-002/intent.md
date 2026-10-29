# SDLC-ARQ-IDEM-002 — Reintentos de checkout y operaciones ya aplicadas devuelven error en vez del resultado original

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §12 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R12.1 Replay idempotente, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-IDEM-001

## Problema
Tras un checkout exitoso, reintentarlo (timeout, reinicio) falla con transición inválida en lugar de devolver el resultado original. El mismo patrón aparece en apertura de turno. Para el usuario parece que la venta falló, lo que induce a repetirla.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sales/use_cases/checkout_use_cases.py:110-115` (sólo la máquina de estados bloquea el segundo checkout)
- `backend/application/cash_register/shift_use_cases.py:69-80`
- Pruebas: `tests/test_procesar_venta_uc_no_duplicate_side_effects.py`, `tests/integration/cash_register/test_cash_ledger_flow.py::test_explicit_idempotency_does_not_duplicate_side_effects` (caja sí); checkout repetido: ninguna.

## Impacto
Cajeros que repiten una venta que sí se cobró; ruido en soporte.

## Objetivo
- Las escrituras críticas (checkout, apertura, cierre, movimientos, devoluciones) devuelven el resultado registrado cuando su `operation_id` ya se aplicó.
- Prueba de aceptación §15 T8 extremo a extremo: venta POS con timeout simulado y reinicio de proceso = una venta.

## Alcance
- **Incluye:** Registro de operaciones procesadas para ventas; replay en casos de uso listados.
- **No incluye:** Pagos (IDEM-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
`cash_processed_operations` (175) ya existe para Caja; reutilizar el patrón.

## Preguntas abiertas
- Ninguna por ahora.
