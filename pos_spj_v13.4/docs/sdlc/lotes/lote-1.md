# Lote 1 — Caja y turnos

- **Rama:** `fix/lote-1`, salida de `sdlc/sdlc-arq-shift-001` (5af0ad0e), comparada contra `claude/erp-financial-bounded-context-uqxz6b`.
- **Fecha:** 2026-11-05/06.
- **Resultado:** 6 ítems LISTO (SHIFT-003 con deuda de permisos declarada). Ninguno BLOQUEADO, DESCARTADO ni en ESPERA.

## Ítems

| Ítem | Estado | Commit | Prueba que lo cubre |
|---|---|---|---|
| SDLC-ARQ-SHIFT-001 | LISTO: construido en `sdlc/sdlc-arq-shift-001`, verificado aquí | 5af0ad0e y anteriores | `test_active_shift_single_source.py`, `test_active_shift_coherence.py`, `test_active_shift_resolver.py`, `test_active_shift_policy.py` |
| SDLC-ARQ-SHIFT-004 | LISTO | 1c42fabd | `tests/integration/cash_register/test_shift_concurrency.py` (13) |
| SDLC-ARQ-SHIFT-002 | LISTO | ecbdd12a, 15a5dfee | `tests/integration/cash_register/test_shift_consultation.py` (11) |
| SDLC-ARQ-SHIFT-003 | LISTO, con 24 permisos sin comprobar pendientes | 03449a47 | `test_shift_permissions_and_handover.py` (21), `tests/architecture/test_cash_permissions_are_checked.py` |
| SDLC-CASH-001 | LISTO | f77f848b | `tests/integration/cash_register/test_sale_reversal_uses_operator_shift.py` (9) |
| SDLC-CASH-002 | LISTO | d9bf8016 | `tests/integration/cash_register/test_cash_deposit_confirmation.py` (17) |

Las pruebas de los cinco ítems nuevos se vieron fallar antes del arreglo.

### SDLC-ARQ-SHIFT-001 (sólo verificación)

Pruebas en verde y diff releído buscando errores de dinero y turnos: no hay defecto. Sus 35 pruebas pasaron; el segmento de Caja completo pasó después de cada ítem.

### SDLC-ARQ-SHIFT-004

- `cash_shifts.version` (DDL de la 175 y migración 358). `set_lifecycle`, `close` y `reassign` comparan estado y versión; 0 filas es `CashShiftConflictError` (hereda de `CashInvalidStateError`).
- La UoW de Caja abre con `BEGIN IMMEDIATE`. Otras UoW siguen con `BEGIN`. Antes de esto la carrera real fallaba con `database is locked`, reproducido en la prueba.
- Abrir con un `operation_id` ya aplicado devuelve el turno original; con otros datos es `CashDuplicateOperationError`.

**Sin resolver:**

- La respuesta "por cajero" se aplicó como regla vigente y se prueba bajo concurrencia, pero **no se quitaron los índices únicos de caja, cajón y terminal** (`ux_cash_shift_active_*`). Quitarlos permitiría dos turnos sobre un mismo cajón y ni el intent ni §8 lo piden. Si "por cajero" significa eso, hay que decirlo.
- `open_cash_shift_handler` (`cash_register_factory.py`) genera un `operation_id` por clic: la idempotencia existe en el caso de uso, pero un doble clic desde la pantalla sigue viéndose como "ya tiene turno".

### SDLC-ARQ-SHIFT-002

- `CashShiftQueryService.list_active`, con `CAJA.turno.ver` y la regla de importes de siempre.
- El presentador expone `consultable_shifts`; la barra dice "Consulta · …". No toca `active_shift_id`, así que quien sólo consulta sigue sin turno.
- Movimientos tiene selector de turno y apaga las escrituras mientras se ve uno ajeno.
- 15a5dfee corrige un defecto propio hallado al releer: sin alcance en la sucursal la barra de Caja reventaba.
- La consulta entre terminales sigue fuera de alcance (SDLC-ARQ-HYB-001).

### SDLC-ARQ-SHIFT-003

- Permisos nuevos `CAJA.turno.intervenir` y `CAJA.movimiento.intervenir`, separados de `forzar_cierre`, que queda para cerrar con Corte Z el turno de otro.
- `CAJA.turno.cerrar` ahora se exige en el Corte Z final.
- `CAJA.corte_z.revisar` se verifica en `ReviewZCutUseCase`: revisión opcional, auditada, una vez por corte, en la pantalla de Corte Z.
- `ReassignCashShiftUseCase`: entrega con `CAJA.turno.reasignar`, motivo obligatorio y evento `CASH_SHIFT_REASSIGNED`. Quien recibe debe poder abrir turnos y no tener otro activo. Sólo OPEN o SUSPENDED. Botón "Entregar turno".
- `cash_shift_assignments` ya se escribe al abrir, entregar y cerrar.
- Estados inalcanzables documentados en `CashShiftStatus`.

**Sin resolver:**

- **24 permisos del catálogo siguen sin comprobarse en el backend.** El intent pide verificarlos o retirarlos, y eso exige decidir cada uno. Están medidos en `SIN_COMPROBAR` de `test_cash_permissions_are_checked.py`; la guardia impide que la lista crezca y obliga a quitar de ella lo que se empiece a comprobar.
- La entrega no exige arqueo y no hay decisión al respecto. Consecuencia: la diferencia del Corte Z recae completa en quien recibió.
- `CASH_SHIFT_REASSIGNED` no se proyecta al central: `central_cash_shifts` conserva al primer cajero (el evento queda `SKIPPED`).
- Asistencia de RR. HH.: sólo ve el cierre del último cajero.
- La revisión del Z no exige otro usuario: la regla no está definida.

### SDLC-CASH-001

- La reversa exige turno operable de quien la hace y escribe ahí la salida, con `related_sale_id`. Sin ese campo el Z del turno B no la restaba de sus ventas y la 1102 quedaba con residuo.
- `CashLedgerRepository.add` rechaza cualquier movimiento en un turno final.
- Una venta sin efectivo sigue sin exigir turno.

**Cambios de comportamiento que conviene revisar:**

- Un supervisor sin turno ya no puede reversar una venta en efectivo; lo pide el intent.
- Nueva validación no pedida de forma literal: no sale más efectivo del que hay en el cajón del operador, igual que en la devolución parcial. Sin ella, un turno recién abierto podía quedar en negativo.

### SDLC-CASH-002

- Respuesta aplicada: confirma tesorería, con ticket.
- **Hallazgo:** además de lo que dice el intent, nadie preparaba depósitos (`cash_deposit_preparations` sin escritor, `CASH_DEPOSIT_PREPARED` sin publicador), así que no había qué confirmar. Se agregó `PrepareCashDepositUseCase`, sobre una entrega ya RECEIVED, con `CAJA.deposito.preparar`.
- `ConfirmCashDepositUseCase` vive en Finanzas, no en Caja: `test_cash_register_domain_contract.py` prohíbe `CASH_DEPOSIT_CONFIRMED`. Se llega por `FinanceCommandService` con `FINANZAS.tesoreria.movimiento`, botón en la pantalla de Tesorería.
- Publica `TREASURY_CASH_DEPOSIT_CONFIRMED` en el `finance_outbox`. Finanzas lo atiende y lo exige con consumidor; el asiento Dr banco / Cr caja va ligado al `deposit_id`, una vez.

**Decisiones tomadas sin respuesta explícita:**

- El ticket es su folio en texto, no un archivo.
- Quien confirma debe ser distinto de quien preparó, igual que en la recepción de entregas.
- El importe es el del depósito preparado: el ticket no lo corrige.

## Migraciones

| # | Archivo | Qué hace |
|---|---|---|
| 358 | `358_cash_shift_version.py` | `cash_shifts.version`, también en el DDL de la 175 |
| 359 | `359_cash_permissions_split.py` | Conserva lo que cada rol podía hacer y da asignación activa a los turnos vivos. Sólo agrega |
| 360 | `360_cash_deposit_confirmations.py` | Tabla `cash_deposit_confirmations` |

- 361 no se usó. Las tres están en `migrations/engine.py` y `MIGRATION_LOG.md`.
- Probadas con `engine.up` sobre una base nueva en el temporal: aplicadas, `foreign_key_check` vacío, permisos presentes.
- **No se probaron sobre una copia de la base real**: no hay una en este worktree.

## Pruebas finales

Todas sobre 15a5dfee, con el árbol limpio.

| Corrida | Resultado |
|---|---|
| `python -m compileall -q .` | rc=0 |
| `tests/architecture` completo | **22 failed, 885 passed**, 1 skipped, 2 xfailed (36:49) |
| Caja, Ventas/POS, Organización, Actualizaciones y Finanzas, unit e integración | **3 failed, 1126 passed**, 15 subtests (22:12) |

Corrida completa de `tests/integration` y `tests/unit` fuera de esas áreas: no se hizo.

## Fallos preexistentes

Ninguno lo introdujo este lote.

- **Arquitectura (22):** el mismo conjunto de `docs/sdlc/baseline/2026-10-28.md`, que también daba 22 (→ SDLC-CORE-008, CORE-009, WA-005). En tres de esas guardias, que podrían ocultar deuda nueva, se revisó el detalle: `test_no_entity_combo_mass_loading`, `test_design_system_guardrails` y `test_no_hardcoded_numeric_defaults_in_ui` no nombran ningún archivo tocado aquí.
- **Segmentos (3):** los mismos de la línea base de `items/SDLC-ARQ-SHIFT-001/plan.md`: dos en `test_sales_checkout_settles_everything.py` (`no such column: sucursal_id`, SDLC-CORE-011) y `test_pos_checkout_dialogs.py::test_reintentar_el_cobro_no_duplica_pagos` (SDLC-CORE-010).

## Fuera de alcance, para el backlog

- **Defecto de dinero, leído y no ejecutado:** `reverse_sale_cash` devuelve el importe completo del cobro aunque la venta ya tenga devoluciones parciales en efectivo; no descuenta `refunded_cash_for_sale`. Inventario sí descuenta lo devuelto.
- `migrations/standalone/354_device_enrollment.py` no está registrada en `engine.py`, tampoco en la rama base.
