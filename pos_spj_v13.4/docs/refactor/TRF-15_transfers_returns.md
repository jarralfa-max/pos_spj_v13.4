# TRF-15 — Devolución al origen

## Flujo canónico

1. `CreateTransferReturnUseCase` crea un documento UUIDv7 contra mercancía físicamente recibida.
2. El origen de la devolución es el destino de la transferencia original; su destino es el origen original.
3. `ApproveTransferReturnUseCase` exige aprobador independiente y coloca la transferencia en `RETURN_IN_PROGRESS`.
4. `DispatchTransferReturnUseCase` registra custodia y mueve el stock a tránsito mediante Inventory.
5. `ReceiveTransferReturnUseCase` registra la custodia en origen, confirma cantidades y peso, y completa el retorno.

## Reglas

- Motivos y estados usan catálogos cerrados.
- Cantidad, peso, piezas, lote y temperaturas usan Decimal y referencias UUID.
- No se puede devolver más de lo físicamente recibido.
- Quien despacha la devolución no puede confirmar su recepción.
- Cada relevo conserva entregador, receptor, ubicación, evidencia, temperatura y fecha.
- Inventory es el único dueño de salida, tránsito y entrada mediante `dispatch_return` y `receive_return`.
- Se publican `TRANSFER_RETURN_CREATED`, tránsito canónico y `TRANSFER_RETURN_COMPLETED`.
