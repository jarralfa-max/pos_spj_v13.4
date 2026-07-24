# TRF-21 — Impresión de Transferencias

## Documentos

El catálogo cerrado incluye documento de transferencia, lista de picking,
documento de embarque, comprobante de recepción y etiqueta de paquete. Los DTO
de impresión contienen únicamente texto ya formateado por QueryServices; los
renderers no consultan repositorios ni recalculan cantidades.

## Pipeline

`PrintTransferDocumentUseCase` revalida el permiso granular correspondiente,
selecciona un renderer por tipo y entrega el artefacto a `TransfersPrintGateway`.
HTML se genera escapando todo valor y las etiquetas portables incluyen barcode
y QR sin acoplarse al lenguaje propietario de una impresora.

## Reimpresión y auditoría

- Cada comando tiene `operation_id` idempotente y entre una y diez copias.
- Una reimpresión referencia una impresión original de la misma transferencia.
- Toda reimpresión exige motivo no vacío.
- Éxitos y fallos del gateway quedan en `transfer_print_log` con actor, impresora,
  copias, formato, archivo, documento, operación y vínculo al original.
- La UI nunca imprime directamente ni decide permisos.
