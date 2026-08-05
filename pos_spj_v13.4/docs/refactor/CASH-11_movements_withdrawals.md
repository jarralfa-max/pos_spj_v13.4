# CASH-11 — Movimientos y retiros

Los motivos de ingreso, retiro y `SAFE_DROP` forman un catálogo cerrado, vigente y desactivable. El comando conserva el código y presenta el nombre configurado como concepto auditable. Un motivo inexistente, inactivo, vencido o perteneciente a otro tipo de movimiento falla de forma cerrada.

Un safe drop es una salida física del cajón y genera exactamente un asiento `SAFE_DROP`. Exige permiso granular, respeta umbral y límite duro, puede exigir autorización independiente por catálogo y nunca puede superar el saldo reconstruido. El evento incluye la decisión de alerta y severidad para los canales configurados.

La entrega a Tesorería representa cambio de custodia del efectivo ya retirado: `PREPARED → DELIVERED → RECEIVED`. Está ligada uno a uno al asiento de safe drop, exige receptor distinto del entregante y no genera una segunda salida del ledger. `CASH_HANDOVER_RECEIVED` solicita a Tesorería registrar su recepción mediante integración por evento; Caja no escribe tablas financieras.
