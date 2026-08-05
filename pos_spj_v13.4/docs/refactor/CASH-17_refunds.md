# CASH-17 — Reembolsos

Un reembolso es distinto de una cancelación total. Conserva UUID propio, venta origen, motivo, solicitante, autorizador y desglose por método. Cada importe solicitado debe ser menor o igual al liquidado originalmente con ese mismo medio; los reembolsos parciales en efectivo se acumulan y nunca pueden superar el efectivo neto recibido por la venta.

Solicitar requiere `CASH_REFUND_REQUEST` y autorizar requiere `CASH_REFUND_AUTHORIZE` con usuarios distintos. Sólo el componente `CASH` crea un asiento `CASH_REFUND` de salida, exige turno abierto y saldo suficiente en el cajón. Tarjeta, transferencia, crédito, puntos, cupones, vales y saldo a favor no alteran efectivo.

Caja consume `SALE_REFUNDED` y publica `CASH_REFUND_PROCESSED` con la porción física y las banderas de integración. Finanzas conserva la compensación contable y Fidelidad revierte puntos mediante sus propios consumidores del evento de Ventas; Caja no escribe ventas, journals, obligaciones comerciales ni saldos de fidelidad.
