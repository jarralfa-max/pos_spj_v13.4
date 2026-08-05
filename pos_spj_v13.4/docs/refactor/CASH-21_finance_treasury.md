# CASH-21 — Finanzas y Tesorería

La integración es exclusivamente por eventos UUIDv7 e idempotentes. Caja nunca
escribe el libro mayor ni tablas de Tesorería; Finanzas nunca modifica turnos,
ledger, cortes, diferencias o entregas de Caja.

## Propiedad de efectos

- `CASH_Z_CUT_GENERATED`: Finanzas mueve el efectivo esperado de cajas POS a
  caja general y reconoce faltante/sobrante en el mismo asiento.
- `CASH_DIFFERENCE_DETECTED`: conserva clasificación y trazabilidad; no duplica
  el efecto ya reconocido por el Corte Z.
- `CASH_REFUND_PROCESSED`: confirma la salida física. Ventas conserva la
  reversión de ingreso, impuestos y costo mediante `SALE_REFUNDED`.
- `CASH_HANDOVER_RECEIVED`: confirma custodia coincidente en Tesorería; no crea
  otro asiento porque el Corte Z ya trasladó el efectivo a caja general.
- `TREASURY_CASH_DEPOSIT_CONFIRMED`: mueve caja general a bancos mediante un
  asiento balanceado, sólo después de confirmarse el depósito.

`finance_processed_events` impide procesar dos veces el mismo evento. El
`PostingEngine` añade una segunda protección por documento, propósito y
operación. No se usa compensación silenciosa ni last-write-wins.

## Validación manual

- Generar Corte Z con faltante y comprobar un solo asiento balanceado.
- Reprocesar cada evento y verificar ausencia de duplicados.
- Confirmar reembolso y entrega sin crear asientos adicionales.
- Confirmar un depósito y revisar débito a bancos y crédito a caja general.
