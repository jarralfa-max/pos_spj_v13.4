# TRF-10 — Despacho

## Alcance implementado

- **Embarques:** `TransferShipment` registra número, transportista/vehículo/conductor, sello, temperatura y líneas.
- **Parciales:** `DispatchTransferShipmentUseCase` detecta embarques parciales y exige `TRANSFERS_PARTIAL_DISPATCH`.
- **Custodia:** cada despacho crea `TransferCustodyEvent` de tipo `ORIGIN_RELEASED` con entregado por, recibido por, vehículo, sello y evidencia.
- **Inventario en tránsito:** el use case consume exclusivamente `InventoryTransferGateway.dispatch`.
- **Eventos:** despacho emite `TRANSFER_DISPATCHED` y, cuando el documento queda totalmente despachado, `TRANSFER_IN_TRANSIT`.

## Decisiones

- Despacho consume picking confirmado; no permite rutas directas desde UI o repositorios legacy.
- La custodia física se guarda separada del documento y del embarque para auditoría posterior.
- El impacto real sobre stock disponible/tránsito pertenece a Inventario vía gateway canónico.

## Tests TRF-10

- Despacho total con gateway de Inventario, custodia y evento in-transit.
- Despacho parcial con permiso granular específico.
- Rechazo de operación duplicada y verificador no independiente.
