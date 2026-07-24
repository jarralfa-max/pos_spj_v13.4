# TRF-6 — Aprobaciones de transferencia

## Alcance implementado

- **Approval workflow:** `ApproveTransferRequestUseCase` aprueba únicamente solicitudes en `PENDING_APPROVAL`.
- **Aprobación total:** si no se envían líneas explícitas, el dominio aprueba las cantidades y pesos solicitados.
- **Aprobación parcial:** si se envían líneas con valores menores o incompletos, el use case exige `TRANSFERS_PARTIAL_APPROVE` y conserva cantidades Decimal-only.
- **Rechazo:** `RejectTransferRequestUseCase` mueve la solicitud a `REJECTED` con permiso granular `TRANSFERS_REJECT`.
- **Segregación:** una transferencia elevada (`URGENT` o `EMERGENCY`) no puede ser aprobada por el mismo solicitante.
- **Idempotencia:** aprobación y rechazo registran `operation_id` mediante el puerto canónico.
- **Eventos:** aprobación y rechazo publican solo `TRANSFER_APPROVED` y `TRANSFER_REJECTED` al sink canónico.

## Decisiones

- Aprobar una solicitud no reserva inventario; TRF-7 conectará reservas mediante use cases de Inventario.
- La aprobación parcial no crea una transferencia separada; ajusta los valores aprobados de las líneas del mismo documento.
- Rechazar no elimina la solicitud, porque el documento conserva trazabilidad y auditoría.

## Tests TRF-6

- Aprobación total con evento canónico.
- Aprobación parcial con permiso granular específico.
- Rechazo con motivo y evento canónico.
- Guardrail de arquitectura para impedir SQL, InventoryEngine y permisos generales en use cases de solicitud/aprobación.
