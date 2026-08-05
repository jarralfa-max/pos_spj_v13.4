# CASH-16 — Entrega de valores

La preparación nace de un `SAFE_DROP` y exige un desglose completo con denominaciones activas y vigentes. La suma debe coincidir exactamente con el importe retirado. El snapshot queda ligado uno a uno al asiento origen y no produce una segunda salida del ledger.

La doble confirmación registra dos operaciones independientes: `DELIVERY`, confirmada por quien entrega, y `RECEPTION`, confirmada por Tesorería con otro usuario. Ambas conservan denominaciones, total, usuario, fecha y `operation_id`. Sólo una recepción que coincide exactamente cambia la custodia a `RECEIVED` y publica `treasury_transfer_required=true`.

Si Tesorería cuenta cantidades o total distintos, la entrega pasa automáticamente a `DISPUTED`, conserva el conteo esperado y recibido y publica `treasury_transfer_required=false`. También puede abrirse una disputa manual con permiso y motivo. Caja publica el resultado por outbox; nunca escribe directamente en Tesorería.
