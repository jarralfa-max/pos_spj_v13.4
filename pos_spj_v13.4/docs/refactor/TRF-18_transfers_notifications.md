# TRF-18 — Notificaciones y WhatsApp

## Policy y canales

`TransferNotificationPolicy` recibe reglas configuradas por evento. In-app es el
canal base; WhatsApp solo se habilita explícitamente para severidades `DANGER` o
`CRITICAL`. La UI no selecciona destinatarios ni envía mensajes.

## Destinatarios

`TransferRecipientQueryService` resuelve usuarios por roles operativos y alcance
de sucursal. El handler no contiene teléfonos, usuarios, roles ni sucursales
hardcodeados. Los roles de una regla pueden incluir origen, destino, almacén,
logística, calidad, gerencia, auditoría o dirección.

## Entrega y auditoría

- `InAppTransferNotifier` y `WhatsAppTransferNotifier` son gateways independientes.
- Cada entrega usa UUIDv7 y la clave idempotente `(event_id, recipient_user_id, channel)`.
- Una entrega confirmada se registra antes de considerarse completada y produce
  una entrada de auditoría `TRANSFER_NOTIFICATION_SENT`.
- Eventos sin regla no producen notificaciones.
- Un destinatario sin dirección WhatsApp conserva su alerta in-app sin fallback
  directo ni envío a un número alternativo.
