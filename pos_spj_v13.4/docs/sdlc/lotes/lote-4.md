# Lote 4 — Mercado Pago (ronda 1)

- **Rama:** `fix/lote-4`, que sale de `claude/erp-financial-bounded-context-uqxz6b` en `e58f6849`.
- **Fechas:** 2026-11-06 a 2026-11-09. El límite de API detuvo el lote una vez; se retomó desde el último
  commit sin rehacer nada.
- **Mandó el intent:** los `intent.md` aprobados el 2026-11-05 (Alfred), con sus respuestas. El backlog
  todavía dice `intent-borrador` y no se editó.

## Estado por ítem

| Ítem | Estado | Commit |
|---|---|---|
| SDLC-PAY-002 | **LISTO** | `65b8cc86` |
| SDLC-PAY-003 | **LISTO** | `26f9fff5` |
| SDLC-PAY-004 | **LISTO** | `4fb14341` |
| SDLC-PAY-005 | **LISTO** | `de9b59df` |
| SDLC-PAY-006 | **BLOQUEADO** | — |
| SDLC-PAY-001 | **LISTO** (entregable de diseño) | `21e9d771` |

### SDLC-PAY-002 — referencia obligatoria y única

Decisión del responsable: «sí» para Tarjeta y Transferencia; no hay ventas en la base.

**Qué cambió:**

- `SalePaymentPolicy.ensure_reference_valid`: obligatoria para MP, CARD y TRANSFER, de 4 a 64 caracteres
  `[A-Za-z0-9._/-]`, sin espacios.
- `RecordSalePaymentUseCase` revisa antes de guardar que no haya otro pago vivo con la misma referencia:
  mismo método y `UPPER(TRIM)`.
- El repositorio traduce la violación del índice a `PaymentReferenceDuplicatedError`. Eso cubre dos cajas
  a la vez.
- Migración **384**: índice único parcial `uq_sale_payments_processor_reference`. El DDL vive en
  `sales_schema.create_payment_reference_index` y no en `create_sales_schema`, que corre desde la 198,
  antes del respaldo legacy de la 255.
- Anular un pago o cancelar la venta libera la referencia.
- El diálogo avisa antes de iniciar el cobro, con el texto de ayuda propio de cada método.

**Reproducción previa:** dos ventas MP con la referencia `123` y otra sin referencia pasaban las tres
(`success=True`).

**Prueba:** `tests/unit/test_sales_payment_reference.py` (34),
`tests/unit/test_pos_checkout_dialogs.py::test_el_dialogo_no_agrega_un_pago_con_referencia_rechazada`.

**Copia de la base real:** 0 pagos y ninguna referencia vacía o repetida; el motor aplica la 384 y
`foreign_key_check` queda vacío.

**Se ajustaron pruebas existentes** que cobraban con tarjeta sin referencia:

- `test_sales_payment.py`
- `test_sales_receipts.py`
- `test_sales_audit_cebf67a.py`
- el doble del presentador en `tests/ui/test_operations_standard_dialogs.py`

### SDLC-PAY-003 — la referencia llega a Caja, Finanzas y ticket

**Qué cambió:**

- `_payment_lines`: una asignación de Caja por pago electrónico, con su `external_reference`.
- `SALE_COMPLETED` lleva `payment_references`. `payments` sigue agregado por método porque Fidelidad y el
  central lo leen así; el central tiene PK `(sale_id, method)`.
- El traductor reparte la liquidación por referencia y tolera eventos viejos.
- La línea del asiento dice `… ref <operación>`.
- El ticket imprime `Ref. Mercado Pago ****1234` (`mask_payment_reference`) en ESC/POS y en la plantilla
  HTML.
- Se eliminó el `PAYMENT_LABELS` muerto de `sale_ticket_escpos_renderer.py`.

**Prueba:** `tests/integration/sales/test_payment_reference_traceability.py` (8), de punta a punta por la
composición real del POS.

### SDLC-PAY-004 — una sola cuenta de procesadores

Decisiones del responsable: una sola cuenta, la venta carga directo y no hay datos que reclasificar.

**Qué cambió:**

- `backend/application/services/finance/treasury_resolution.py` es la única resolución de cuenta de
  tesorería. La usan:
  - la venta (`SaleCompletedHandler`);
  - la devolución (`SaleReturnedHandler`);
  - las compras (`procurement_immediate_payment_bridge`).
- Las tres llegan al mismo espejo (1115). Sin exactamente una cuenta, el evento falla a la vista en vez
  de caer en la 1120.
- El alta rechaza una segunda cuenta de procesador.
- Migración **385**: renombra la cuenta sembrada a «Procesadores de pago (Mercado Pago y tarjetas)».

**Prueba:** `tests/integration/finance/test_processor_account_mirror.py` (12).

**Copia de la base real:** 0 renglones contables, así que la 1120 no tiene saldo; la 385 renombra la
cuenta.

### SDLC-PAY-005 — Corte X/Z por medio de pago

**Qué cambió:**

- `backend/domain/cash_register/cut_breakdown.py` (dominio puro): conteo y bruto por efectivo, tarjeta,
  Mercado Pago, transferencia, vales, crédito y otros; ventas con pago mixto; reembolsos a medio
  electrónico.
- El X y el Z lo agregan a su `snapshot` leyendo `payment_allocations` y `cash_refund_executions` del
  turno.
- Los documentos impresos muestran el desglose a quien ve importes.
- El efectivo esperado y el formato no cambian.

**Prueba:** `tests/integration/cash_register/test_cut_payment_breakdown.py` (4).

**Pendientes de PAY-008/018:** los pagos pendientes y las comisiones no existen todavía, así que no se
muestran.

### SDLC-PAY-006 — BLOQUEADO

El problema sigue:

- `refund_integration.py:130-155` crea `CashRefundExecution` con `ORIGINAL_PAYMENT_METHOD` ya ejecutado.
- `SaleReturnedHandler` abona el procesador al devolver.
- `ReverseSaleUseCase` sólo compensa efectivo (`return_use_cases.py:258-263`).
- `SaleReversedHandler` revierte el asiento completo en el acto.

Para que «el asiento se emite al confirmar» hacen falta **decisiones contables sin responder**:

1. ¿En qué cuenta queda un reembolso electrónico **solicitado y aún no confirmado**? Por ejemplo, una
   cuenta nueva de pasivo «Reembolsos por pagar a clientes». ¿O se difiere todo el asiento de la
   devolución hasta confirmar?
2. En el **reverso** de una venta MP, el asiento de reversa abona hoy el procesador en el acto. ¿Pasa por
   la misma cuenta transitoria hasta confirmar?
3. Si el reembolso se **rechaza**, ¿qué pasa con la devolución ya registrada? ¿Efectivo, vale, saldo a
   favor o se revierte?

La pregunta respondida (el cajero confirma con su permiso y avisa al gerente) no basta. No se escribió
código.

**Hallazgo lateral, no corregido:** en una devolución mixta (efectivo y tarjeta),
`CashRefundExecution` guarda sólo el monto en efectivo con método `CASH`. La porción electrónica no deja
renglón de ejecución.

### SDLC-PAY-001 — diseño, sin código

**Documentos nuevos en `docs/architecture/`:**

- `MERCADO_PAGO_INTEGRATION_TRD.md`
- `MERCADO_PAGO_INTEGRATION_APPFLOW.md`
- `MERCADO_PAGO_INTEGRATION_DATA_MODEL.md`
- `MERCADO_PAGO_INTEGRATION_SECURITY.md`
- `MERCADO_PAGO_INTEGRATION_UX.md`
- `MERCADO_PAGO_INTEGRATION_TEST_PLAN.md`
- `MERCADO_PAGO_INTEGRATION_ADR.md`

Se actualizaron `ventas_official_flow.md` y `FINANCIAL_TRACEABILITY_END_TO_END.md` §4.3, que describían el
flujo legacy ya eliminado.

**Decisiones en el ADR:**

- **Aprobadas por el responsable:**
  - token temporalmente en cada caja;
  - ngrok;
  - una cuenta cobradora por empresa;
  - una cuenta de procesadores.
- **Propuestas, por aprobar:**
  - `PaymentProviderPort` nuevo en lugar de extender `PaymentTerminalGateway`;
  - `httpx` en lugar del SDK.

**Para el backlog:**

- **Conflicto de fuentes:** la respuesta «token en cada caja» contradice `PLAN-MAESTRO.md` decisión 1 y
  `mercado-pago.md` §12.1/§18. Hay que registrar como pregunta abierta su criterio de salida.
- **Archivo perdido:** `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md` no está en la rama base. Sólo
  existe en `0d8c5844`, y el enlace de `matriz-mercado-pago.md` está roto.

## Migraciones

| N.º | Archivo | Qué hace |
|---|---|---|
| 384 | `384_sale_payment_reference_unique.py` | Índice único parcial de la referencia de procesador |
| 385 | `385_single_processor_account.py` | Renombra la cuenta de procesadores; avisa si la 1120 tiene renglones |

Las dos están registradas en `migrations/engine.py` y documentadas en `MIGRATION_LOG.md`. Se probaron con
`engine.up()` sobre una copia temporal de `data/spj_pos_database.db`, abierta en sólo lectura y copiada con
`backup()`.

## Pruebas

RESULTADOS_PRUEBAS

## Choques previsibles con otros lotes

- **`fix/lote-1` (Caja)** toca:
  - `z_cut_use_cases.py`: aquí cambia una línea del import y una tras `_snapshot`; los hunks de lote-1
    son otros.
  - `cash_register_factory.py`: hunks distintos.
  - `repositories.py` de Caja y `sales_cash_effects_client.py`: +10 líneas en lote-1.
  - `refund_integration.py`, `checkout_use_cases.py` y `return_use_cases.py`.
- **`fix/lote-2` (Finanzas)** toca `procurement_immediate_payment_bridge.py`: agrega
  `register_purchased_asset_in`. Aquí se reemplazó el filtro de candidatos por `treasury_candidates`. Se
  espera una fusión limpia o trivial.
- **`migrations/engine.py` y `MIGRATION_LOG.md`:** todos los lotes agregan al final. Choque de texto
  seguro; las versiones no chocan (lote-1 usa 358-360, lote-2 380-381, este 384-385).

## Fallos preexistentes vistos (no causados por este lote)

- `tests/integration/test_sales_checkout_settles_everything.py`: 2 fallos
  (`test_con_autorizacion_y_motivo_…` y `test_la_autorizacion_sin_existencia_se_valida[sin_permiso]`).
  La causa es `no such column: sucursal_id`, la familia SDLC-CORE-011 de la línea base. Se confirmó en la
  rama base con `git stash`.
- `tests/unit/test_pos_checkout_dialogs.py::test_reintentar_el_cobro_no_duplica_pagos`: en la línea base
  (SDLC-CORE-010).
- `tests/ui/test_operations_standard_dialogs.py`:
  - `test_payment_enter_adds_local_line_and_cancel_never_starts_checkout` falla porque busca un botón
    «Cancelar» que desde V03 dice «Cerrar».
  - `test_payment_retry_keeps_recorded_lines_and_accepts_once` **se cuelga**: un diálogo modal se abre en
    la prueba. Igual en la rama base, medido con `git stash`.
- Nota: el ayudante `_confirm_immediate_purchase` de `test_immediate_payment_bridge.py` sólo funciona con
  el `conftest` de `tests/integration/procurement/`. Desde otra carpeta, Compras deniega
  («AuthorizationChecker no configurado»), así que la prueba de PAY-004 llama al puente directamente.
