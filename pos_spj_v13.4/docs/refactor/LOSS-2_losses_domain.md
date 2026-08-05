# LOSS-2 — Dominio base de Losses

Estado: `IMPLEMENTED_WITH_TEST_ENVIRONMENT_BLOCKER` (2026-08-02).

## Entidades

- `LossCase`: aggregate root con identidad UUIDv7 distinta de `operation_id`.
- `LossLine`: producto, lote, ubicación, piezas/cantidad, peso, costo y valor recuperable usando Decimal.
- `LossClassification`: clasificación canónica configurable y activable.
- `LossReason`: causa/motivo configurable asociado a una clasificación.

## Catálogos y estados

Se incorporaron las clasificaciones y orígenes solicitados, además de `THEORETICAL_LOSS` para representar el concepto sin movimiento físico. El workflow protegido incluye:

```text
DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED -> INVENTORY_POSTED -> CLOSED
                      \-> REJECTED -------------------------------> CLOSED
```

También se reservan estados de investigación, tratamiento, reverso y cancelación para fases posteriores. No se implementaron transiciones sin caso de uso todavía.

## Policies

- `LossRegistrationPolicy`: decide si hay posting físico y valida origen/documento.
- `LossClassificationPolicy`: impide tratar coproductos/subproductos como merma automática.
- `LossApprovalPolicy`: umbral Decimal obligatorio, recibido desde configuración.
- LOSS-1 conserva autorización, scopes, límites y segregación en aplicación.

## Eventos

`LossEvents` y `build_loss_event()` generan envelopes JSON-safe con UUIDv7 independientes para evento, operación y entidad. Decimal se serializa como string. No se publica ningún evento en esta fase; la publicación/outbox pertenece a LOSS-3 y casos de uso posteriores.

## Pruebas agregadas

- `tests/unit/losses/test_loss_entities.py`
- `tests/unit/losses/test_loss_catalogs_and_policies.py`
- `tests/unit/losses/test_loss_events.py`
- `tests/architecture/test_losses_domain_contract.py`

## Validación

- Compileall del dominio/aplicación/pruebas Losses: `PASSED`.
- Smoke de workflow completo, valuación y evento: `PASSED`.
- Pytest: `BLOCKED`; el Python global y los entornos virtuales disponibles no incluyen `pytest`.

## Límites de fase

No se modificó schema, UI, navegación, repositorios, inventario ni la ruta legacy `modulos/merma.py`. No existe escritura dual. LOSS-3 deberá crear schema born-clean, constraints, índices, outbox e idempotencia después de ejecutar la suite LOSS-1/LOSS-2 con pytest disponible.
