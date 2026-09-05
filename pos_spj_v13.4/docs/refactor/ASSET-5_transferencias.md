# ASSET-5 — Transferencias (Activos / EAM)

Ejecutado: 2026-09-02. §20, §65 (parcial) del prompt maestro.

## Qué se construyó

`backend/domain/assets/entities/asset_transfer.py` — `AssetTransfer`. Nunca cambiar sucursal mediante `UPDATE` directo (§20 lo prohíbe explícitamente) — toda relocalización entre sucursales pasa por esta máquina de estados guardada:

```text
REQUESTED → APPROVED → PREPARED → IN_TRANSIT → RECEIVED
REQUESTED | APPROVED → REJECTED   (solo antes de enviar)
cualquier estado no terminal → CANCELLED
```

Nuevo enum `AssetTransferStatus`. Excepciones nuevas: `AssetTransferNotFoundError`, `AssetTransferNotAllowedError`. Eventos: los 5 de §87 ya existían desde ASSET-3 (`ASSET_TRANSFER_REQUESTED/APPROVED/SHIPPED/RECEIVED/REJECTED`); se agregaron `ASSET_TRANSFER_PREPARED` y `ASSET_TRANSFER_CANCELLED`, que el listado de eventos del prompt maestro (§87) no enumera explícitamente pero que los estados PREPARED/CANCELLED de §20 sí requieren para tener trazabilidad completa. Port nuevo: `AssetTransferRepositoryPort`.

## Regla de negocio real, no solo un permiso

`receive()` implementa §84 literalmente en el dominio, no solo como un permiso que se podría verificar o no en la UI: **lanza `SegregationOfDutiesError` si `received_by == requested_by`** — quien solicitó una transferencia no puede confirmar su propia recepción. Cubierto por test explícito (`test_requester_cannot_receive_own_transfer`).

## Explícitamente fuera de alcance

Use cases de aplicación (`RequestAssetTransferUseCase`, `ApproveAssetTransferUseCase`, etc.) no construidos — mismo motivo que ASSET-4 (sin infraestructura de persistencia todavía).

## Tests

`tests/unit/assets/test_asset_transfer.py` — ciclo feliz completo, guards de cada transición inválida (enviar antes de preparar, rechazar después de enviar, cancelar desde estado terminal), y el test de segregación de funciones. Ver `ASSET-4_custodia.md` para el conteo agregado de la suite.

## Siguiente fase

ASSET-6 — Mantenimiento.
