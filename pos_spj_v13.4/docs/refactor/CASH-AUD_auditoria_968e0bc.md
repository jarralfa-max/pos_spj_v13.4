# CASH-AUD — Respuesta a la auditoría de código de Caja (968e0bc)

Fecha: 2026-10-16. Auditoría recibida: «Auditoría de código: módulo Caja» sobre
`968e0bcf` (8 hallazgos, CJA-01..08). Cada hallazgo se comprobó contra el código
actual; los críticos se reprodujeron. Sin migración (no cambia el esquema).
Pruebas nuevas: `tests/integration/cash_register/test_cash_audit_968e0bc.py` (14)
y `tests/architecture/test_cash_register_sales_single_path.py` (1).

## Medido en la base real

* **4 eventos de Caja PENDIENTES desde el 2026-10-11** sin llegar a Finanzas
  (CJA-04): se despachan al arrancar (verificado en copia).
* **Dos cajas** activas en la sucursal («Caja Principal», «Cadenas01»): con la
  elección «primera activa» (CJA-07) el riesgo era real.
* 0 ventas del mostrador cobradas sin su registro en Caja (CJA-03).

## Hallazgo por hallazgo

| # | Prior. | Estado | Qué se hizo | Prueba |
|---|---|---|---|---|
| CJA-01 | Crítica | Cerrado | UNA regla (`backend/application/cash_register/amount_visibility.py`): con arqueo ciego abierto nadie ve importes del turno —saldo, totales ni el monto de cada movimiento— salvo un supervisor con `CAJA.conteo.ver_esperado` que no sea el cajero; sin arqueo, el cajero ve su turno y los ajenos exigen `CAJA.ver.importes_sensibles`. Aplicada al libro de movimientos (ahora exige usuario, sucursal y `CAJA.movimiento.ver`, y valida que el turno sea de la sucursal), a la lista de turnos (esperado y fondo inicial ajeno) y al resumen (fondo inicial, diferencias, montos de entrega y esperado). El Corte X ya estaba bloqueado durante el arqueo. | `TestBlindCountDoesNotLeak` (4), `test_cash_overview_query_service` |
| CJA-02 | Alta | Cerrado | `shift_ownership.py`: el titular opera su turno; intervenir el de otro exige el permiso de intervención (`turno.forzar_cierre` para suspender/reanudar/pre-cerrar, Corte Z y movimientos; `conteo.sobrescribir` para arquear un turno ajeno; `ver.importes_sensibles` para el Corte X) y, en transiciones, MOTIVO; el evento queda marcado `intervention`. Abrir turno a nombre de otro exige `turno.reasignar`. Sin permisos nuevos: el gerente ya los tiene, el cajero no. | `TestShiftOwnership` (4) |
| CJA-03 | Alta | Ya cerrado + conciliación | Desde la auditoría de Ventas V06 (2026-10-15) el cobro, la devolución y el reverso del mostrador registran Caja DENTRO de su transacción: no pueden divergir. Los manejadores Venta→Caja quedan documentados como «no suscribir» con guarda de arquitectura (duplicarían el efectivo). Conciliación visible: indicador «Ventas sin registro en Caja» en el resumen (hoy 0 en la base real). | guarda de arquitectura |
| CJA-04 | Alta | Cerrado | El arranque despacha `cash_outbox`; además un servicio de fondo lo reintenta cada 2 minutos (`cash_register.outbox`). Indicador «Envíos a Finanzas» en el resumen: pendientes, agotados (`DEAD_LETTER`) y desde cuándo. | `test_startup_drains_the_cash_outbox`; copia real: 4 → 0 |
| CJA-05 | Media | Cerrado | Cortes X/Z: caja, cajero, apertura del turno y quien lo generó por NOMBRE (antes UUID del turno, usuario y conteo). El código de barras lleva el FOLIO del corte y es un símbolo rasterizado; ya no se imprime `QR:<uuid>`/`BARCODE:` como texto (el QR del UUID se quitó: no servía para verificar nada). El concepto del movimiento de venta usa el folio comercial (`Venta V-COR-000008`) y los movimientos viejos se muestran con el folio al leer. Lecturas operativas: «quién» o «qué caja» por nombre en vez del id. | `test_cut_tickets_print_real_symbols…` |
| CJA-06 | Media | Cerrado | Un permiso EFECTIVO por documento: Corte X `corte_x.imprimir/reimprimir`, Corte Z `corte_z.*`, el resto `CAJA.imprimir/reimprimir` (`PrintCashDocumentCommand.permission_code`). El despacho de la cola entrega trabajos ya autorizados y sólo pide acceso a Caja. | `test_a_role_with_the_cut_permission_alone…` |
| CJA-07 | Media | Cerrado | El resolvedor ya no toma «la primera activa»: turno propio → caja elegida en la estación (si sigue siendo de la sucursal, activa y libre) → la ÚNICA libre → ninguna. Abrir turno muestra un selector «Caja · Cajón · Terminal» con las libres. | `TestRegisterChoice` (2) |
| CJA-08 | Media | Cerrado | `CAJA.ver.sucursales_asignadas` ahora concede las sucursales asignadas de la sesión (`assigned_branch_ids`), no sólo la activa. | `test_assigned_branches_are_honoured` |

## Pendientes cerrados (2026-10-16)

* **Lista de entregas de valores validada en el backend.**
  `CashHandoverQueryService.list_for_branch(branch_id, requester_user_id=...)`
  exige `HANDOVER_VIEW`; el monto sólo lo ve quien preparó la entrega o quien
  tiene `VIEW_SENSITIVE_AMOUNTS`/`HANDOVER_RECEIVE` (para los demás `amount=None`).
  Las filas traen además el nombre de quién preparó, entregó y recibió.
* **Sin `display_code` en pantallas de Caja.** El libro trae `origin_label`
  («Venta V-COR-000008», «Devolución de venta …», «Apertura del turno») y
  `reversal_label` (concepto + hora del movimiento revertido) calculados en el
  backend; los turnos se muestran como «Caja · cajero · dd/mm hh:mm»
  (`backend/application/cash_register/shift_labels.py`); la cola de sincronización
  muestra «Operación #N». El UUID queda sólo como clave interna.
* Pruebas: `test_handover_amounts_follow_who_prepared_or_receives`,
  `test_ledger_rows_carry_readable_origin` en
  `tests/integration/cash_register/test_cash_audit_968e0bc.py`.

Sin pendientes abiertos de esta auditoría.
