# LOYALTY_REFACTOR_AUDIT

## Ruta actual auditada
1. `SalesService.execute_sale` calcula canje y dispara persistencia de venta.
2. `LoyaltyService` acredita/canjea puntos y publica eventos.
3. Finanzas registra asientos y pasivo de fidelidad.
4. Ticket renderiza `puntos_ganados` y `puntos_totales`.

## Hallazgos
- Existía acoplamiento a `modulos.growth_engine` desde `core/services/loyalty_service.py`.
- Existían lecturas/escrituras SQL en UI de fidelidad.
- Idempotencia parcial en ledger, sin constraint único global.

## Refactor aplicado (incremental)
- Se creó `repositories/loyalty_repository.py` para consolidar SQL operativo.
- Se creó `application/services/loyalty_application_service.py` para casos de uso idempotentes.
- Se agregó migración `092_loyalty_ledger_canonicalization.py` con `UNIQUE(cliente_id,tipo,referencia)`.
- Se agregaron eventos loyalty explícitos en `event_bus.py`.

## Legacy
`modulos/growth_engine.py` permanece como shim temporal hasta cerrar migración total en fases siguientes.
