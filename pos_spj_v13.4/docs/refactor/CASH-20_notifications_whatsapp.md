# CASH-20 — Notificaciones y WhatsApp

Las alertas de Caja se convierten en trabajos persistentes mediante la policy
efectiva más específica: sucursal antes que sistema, respetando vigencias. Cada
policy determina severidad y canales; sus destinatarios activos se resuelven por
canal.

## Canales

- `IN_APP`: crea una alerta persistente para un usuario UUIDv7.
- `WHATSAPP`: exige un destinatario E.164 y usa un sender inyectado.
- `EMAIL`: es opcional; sin sender configurado queda `SKIPPED` y auditado.

Los casos de uso nunca importan SDKs de proveedores. WhatsApp y email se conectan
en el composition root mediante `CashNotificationSender`.

## Entrega confiable

La combinación `(source_event_id, channel, recipient)` es única. Preparar o
reprocesar el mismo evento no duplica mensajes. Cada intento tiene UUIDv7,
resultado, referencia del proveedor, código de error y auditoría. Los fallos se
reintentan con backoff exponencial y terminan en `DEAD_LETTER` al agotar el límite.
Los detalles internos del proveedor no se almacenan ni se muestran al usuario.

## Validación manual

- Generar una diferencia crítica y comprobar los destinatarios de la sucursal.
- Abrir la bandeja in-app con el usuario destinatario.
- Validar el teléfono WhatsApp en E.164 y la plantilla visible.
- Deshabilitar email y comprobar `SKIPPED` sin afectar los otros canales.
- Reprocesar el evento y verificar que no aparecen trabajos duplicados.
