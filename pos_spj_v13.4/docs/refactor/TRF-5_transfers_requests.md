# TRF-5 — Solicitudes de transferencia

## Alcance implementado

- **Creación:** `CreateTransferRequestUseCase` crea solicitudes `DRAFT` con número humano provisto por un puerto, UUIDv7 de dominio y líneas Decimal-only.
- **Edición:** `EditTransferRequestUseCase` reemplaza líneas y prioridad únicamente mientras la solicitud permanece en `DRAFT`.
- **Envío:** `SubmitTransferRequestUseCase` mueve el agregado de `DRAFT` a `PENDING_APPROVAL`.
- **Prioridad:** el dominio valida el catálogo cerrado `LOW`, `NORMAL`, `HIGH`, `URGENT`, `EMERGENCY`.
- **Seguridad:** cada use case revalida permisos granulares y alcance desde backend.
- **Idempotencia:** cada operación consulta `operation_exists` antes de mutar el agregado.
- **Eventos:** creación y envío emiten eventos canónicos a un sink post-commit/outbox; la edición no publica nombres legacy ni toca inventario.

## Decisiones

- La solicitud no reserva ni mueve inventario.
- La UI queda fuera de persistencia: consume DTOs y use cases, no repositorios ni SQL.
- El generador de número es un puerto para permitir una secuencia transaccional posterior sin usar `MAX(id)+1`.

## Tests TRF-5

- Creación con permisos, prioridad y evento `TRANSFER_REQUEST_CREATED`.
- Rechazo de operación duplicada.
- Edición permitida solo en `DRAFT`.
- Envío con permiso granular y evento `TRANSFER_REQUEST_SUBMITTED`.
- Arquitectura: los use cases de solicitud no importan SQLite ni gateways de inventario.
