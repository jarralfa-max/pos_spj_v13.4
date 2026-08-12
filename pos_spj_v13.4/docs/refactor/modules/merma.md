# Módulo Mermas y Pérdidas

## Estado

`LOSS-23 COMPLETE — bounded context canónico, sin ruta waste legacy.`

## Ruta única

- UI: `frontend/desktop/modules/losses/`.
- Aplicación: `backend/application/losses/`.
- Dominio: `backend/domain/losses/`.
- Persistencia: `backend/infrastructure/persistence/loss_*`.
- Esquema: `migrations/standalone/174_losses_bounded_context_schema.py`.
- Inventario: `LossInventoryIntegrationService` sobre el ledger canónico.

No existen `modulos/merma.py`, `WasteApplicationService`, `WasteType`, tabla
`mermas` ni `inventory_waste_event`. El detalle del corte y las instrucciones
born-clean están en [LOSS_23_LEGACY_REMOVAL_REPORT.md](../LOSS_23_LEGACY_REMOVAL_REPORT.md).
