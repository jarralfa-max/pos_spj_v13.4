# CASH-19 — Offline-first

El outbox de Caja sigue siendo parte de la transacción de negocio. CASH-19 añade
una capa de transporte separada que asigna a cada evento una secuencia monotónica
por dispositivo sin usarla como identidad: dispositivos, sobres, eventos y
operaciones conservan UUIDv7.

## Ciclo

1. Los eventos pendientes de la sucursal se convierten atómicamente en sobres.
2. Un lote se marca `IN_FLIGHT` antes de abandonar SQLite.
3. El transporte recibe evento, operación, entidad, versión y secuencia.
4. `ACCEPTED` confirma outbox y revisión remota.
5. Una caída programa `RETRY` con backoff exponencial limitado a 15 minutos.
6. `CONFLICT` conserva ambas revisiones, bloquea entregas posteriores y exige
   resolución autorizada con motivo (`RETRY_LOCAL` o `ACCEPT_REMOTE`).

Los estados del nodo son `IDLE`, `SYNCING`, `RETRYING`, `CONFLICT` y `ERROR`,
independientes de la conectividad `ONLINE/OFFLINE`. La consulta de estado expone
secuencias y contadores sin permitir SQL desde UI. No existe resolución automática
last-write-wins para movimientos financieros.

## Checklist manual

- Desconectar la red, operar Caja y comprobar que la operación local termina.
- Reconectar y verificar orden de entrega y confirmación del outbox.
- Simular timeout y revisar la siguiente fecha de intento.
- Simular revisión remota incompatible y confirmar que los eventos posteriores
  no se envían hasta resolver el conflicto.
