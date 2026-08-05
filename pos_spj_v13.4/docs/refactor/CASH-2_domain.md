# CASH-2 — Dominio canónico de Caja

Fecha: 2026-08-03  
Estado: `IMPLEMENTED` como dominio puro. Persistencia y orquestación corresponden a CASH-3/CASH-4.

## Entidades y documentos

- `CashRegister`: caja física activable/bloqueable y perteneciente a una sucursal.
- `CashDrawer`: cajón con identidad propia, separado de la caja.
- `PosTerminal`: terminal POS con identidad propia.
- `CashShift`: turno con estados `OPEN`, `SUSPENDED`, `CLOSING`, `CLOSED`; exige un Corte Z para cerrar.
- `CashLedgerEntry`: movimiento inmutable, UUIDv7, dirección explícita y `operation_id` idempotente.
- `CashLedger`: proyección reconstruible; el saldo es suma de movimientos firmados y no un campo mutable.
- `BlindCashCount`: captura por denominación; deliberadamente no tiene `expected_amount` y se bloquea al confirmar.
- `XCut`: documento informativo no final; no modifica ni cierra el turno.
- `ZCut`: documento final ligado a conteo ciego, con esperado, contado y diferencia Decimal.
- `CashDifference`: workflow `DETECTED → EXPLAINED → UNDER_REVIEW → RESOLVED` con usuarios independientes.
- `CashHandover`: workflow `PREPARED → DELIVERED → RECEIVED`, con doble confirmación de custodia.

## Policies

- `CashClosingPolicy`: exige turno en cierre, conteo ciego confirmado, cero operaciones pendientes y un solo Corte Z final.
- `CashDeviceAvailabilityPolicy`: caja, cajón y terminal deben estar activos para operar.
- Se conservan las policies CASH-1 de límites, segregación y autorización.

## Contratos

- Toda identidad creada por el dominio usa `backend.shared.ids.new_uuid()` y UUIDv7.
- Todo monto usa `Decimal`; `float` se rechaza explícitamente.
- Estados, movimientos y direcciones son enums cerrados.
- No hay SQL, repositorios, infraestructura ni PyQt en dominio.
- Los eventos incluyen `event_id`, `operation_id`, `entity_id`, `branch_id`, `user_id`, timestamp UTC, `source_module` y payload.
- `event_id`, `operation_id` y `entity_id` son distintos.

## Eventos canónicos

El catálogo cubre cajas, cajones, terminales, turnos, ledger, conteo ciego, Corte X, Corte Z, diferencias y entregas. No admite nombres legacy `CAJA_*`.

## Tests

```text
tests/unit/cash_register/test_cash_register_domain.py
tests/unit/cash_register/test_cash_register_security.py
tests/architecture/test_cash_register_domain_contract.py
tests/architecture/test_cash_register_security_foundation.py
```

Riesgos pendientes:

- El schema actual todavía usa tablas legacy y `REAL`.
- Falta repositorio/UnitOfWork/outbox.
- Falta integrar Ventas para crear movimientos de efectivo idempotentes.
- Falta persistir el bloqueo de un único turno por caja/cajón/cajero.
- Falta persistir `UNIQUE(cash_shift_id, final_z_cut)` y `UNIQUE(operation_id)`.

Siguiente fase: CASH-3 — esquema born-clean UUIDv7, constraints, índices, idempotencia y bootstrap.
