# LOSS-11 — Calidad y decomisos

## Alcance

- Rechazo de calidad con bloqueo físico mediante la cuarentena canónica de Inventario.
- Decomiso de un lote previamente bloqueado mediante la disposición canónica.
- Contaminación `NONE`, `SUSPECTED` o `CONFIRMED` como dato estructurado.
- Lectura de temperatura `Decimal` contra un rango explícito y registro en cadena de frío.
- Evidencias inmutables con URI, checksum SHA-256, tipo y metadatos JSON.
- Idempotencia, outbox, UUIDv7, alcance organizacional y transacción compartida.

## Reglas protegidas

1. Toda decisión requiere evidencia y observaciones.
2. El decomiso requiere contaminación confirmada o temperatura fuera de rango.
3. El decomiso sólo procede sobre una cuarentena activa.
4. Quien bloqueó el lote no puede ejecutar su decomiso.
5. Losses nunca actualiza directamente saldos, lotes, cuarentenas ni cadena de frío.
6. Una falla de Inventario revierte también evaluación, evidencia y estado del expediente.

## Persistencia

La migración `174_losses_bounded_context_schema.py` incorpora
`loss_quality_assessments` y `loss_quality_evidence`. Se reutilizan
`loss_evidence`, `loss_dispositions`, `loss_outbox` y
`loss_processed_operations`.

## Permisos

- `LOSSES_QUALITY_REJECT` para rechazar y bloquear.
- `LOSSES_QUALITY_CONDEMN` para ejecutar el decomiso.
- Inventario conserva sus permisos propios para temperatura, cuarentena y disposición.

## Validación manual

1. Registrar un expediente de contaminación con lote y evidencia.
2. Rechazarlo con una lectura fuera de rango y comprobar la cuarentena.
3. Confirmar que el mismo inspector no puede decomisar.
4. Completar el decomiso con otro usuario autorizado.
5. Verificar expediente cerrado, disposición, evidencia, ledger y ambos outbox.
