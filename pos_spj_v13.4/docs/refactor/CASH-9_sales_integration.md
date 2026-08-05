# CASH-9 — Integración con Ventas

Ventas conserva la propiedad del cobro y publica el resultado liquidado. Caja consume el evento mediante una frontera anticorrupción y exige un turno `OPEN` del cajero en la misma sucursal para cualquier venta, incluso cuando no contiene efectivo.

El ledger registra sólo el efectivo neto que entra al cajón: suma las líneas `cash`/`efectivo` y resta el cambio. Tarjeta, transferencia, crédito y procesadores permanecen en sus liquidaciones financieras y no alteran el saldo físico. Un pago mixto produce un único asiento `CASH_SALE` por su componente efectivo, ligado al UUID de la venta.

`SALE_CANCELLED` y `SALE_REFUNDED` producen un asiento compensatorio `REVERSAL`; nunca editan el asiento original. La referencia única por venta, el `operation_id` y el reverso único hacen seguros los reintentos. Movimiento, auditoría, evento y outbox se confirman juntos en `CashRegisterUnitOfWork`.
