# Backend and Frontend Language Rules

## Mandatory language split

- Backend code must use English for modules, classes, functions, commands, DTOs, events, schemas, APIs, and internal identifiers.
- User-visible frontend text must be Spanish.
- Database-neutral technical concepts should be named in English in backend code.
- Spanish is allowed for existing database column names or legacy persisted data until a tested migration plan exists.

## Backend naming examples

Use English names such as:

- `CreateSaleUseCase`
- `RegisterWasteUseCase`
- `CustomerQueryService`
- `InventoryMovementRecorded`
- `PurchasePlanningService`

Avoid new backend names such as:

- `CrearVentaUseCase`
- `ServicioMerma`
- `ConsultaClienteService`

## Frontend text examples

Use Spanish user-facing labels such as:

- `Cliente`
- `Producto`
- `Cantidad`
- `Registrar merma`
- `Generar corte Z`

Avoid exposing backend-only English to end users unless it is a brand, API term, or technical diagnostic.

## DTOs and events

DTO fields and event payload keys should be English to support a future API and integrations. UI adapters may translate labels and validation messages into Spanish.

## Error messages

- Domain and application errors should expose stable English error codes.
- UI should map error codes to Spanish messages.
- Logs may include English technical context and must not replace Spanish user-visible feedback.
