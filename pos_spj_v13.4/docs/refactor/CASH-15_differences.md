# CASH-15 — Diferencias

Toda diferencia no cero se clasifica como `SHORTAGE` o `OVERAGE`. Una política vigente por sucursal define tolerancia, umbral crítico, ventana y umbral de reincidencia, además de los canales de alerta. Dentro de tolerancia se conserva la trazabilidad sin alertar; fuera de tolerancia se marca `REVIEW`, y por monto o reincidencia se eleva a `CRITICAL`.

La detección conserva responsable, importe, tolerancia aplicada y número de reincidencia. Genera `CASH_DIFFERENCE_DETECTED` dentro de la transacción del Corte Z. El payload solicita `IN_APP`, `EMAIL` o `WHATSAPP` según configuración; Caja nunca invoca directamente proveedores de mensajería y los destinatarios E.164 se resuelven en el despachador.

El workflow es `DETECTED → EXPLAINED → UNDER_REVIEW → RESOLVED`. Explicar, revisar y resolver tienen permisos separados, operaciones idempotentes, auditoría y eventos propios. Quien explicó no puede revisar, y quien detectó, explicó o revisó no puede resolver.
