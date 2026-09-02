# ORD-11 — Aprobación del cliente

Fecha: 2026-08-31. Alcance: master prompt §27 (idempotencia, expiración) — Aceptación y
Rechazo ya quedaron cubiertos por ORD-10 (`AcceptWeightAdjustmentUseCase`/
`RejectWeightAdjustmentUseCase`); revisado el solape antes de construir esta fase, tal
como quedó anotado en memoria.

## Qué se construyó

- **Idempotencia**: `CustomerOrderLine.accept_customer_adjustment()`/
  `reject_customer_adjustment()` ahora son idempotentes — repetir la misma decisión
  (doble tap en WhatsApp, reintento de webhook) es un no-op, no un error. Solo un
  conflicto real (aceptar una línea ya rechazada, o viceversa) sigue lanzando
  `InvalidOrderStateError`.
- **Expiración**: `customer_approval_expires_at` (campo nuevo en `CustomerOrder`),
  `CustomerOrder.expire_customer_approval(now=...)` — trata cada línea todavía
  `PENDING_CUSTOMER_APPROVAL` como rechazo implícito y pone
  `customer_approval_status=EXPIRED`. `ApprovalExpirationNotDueError` (mirror de
  `OrderActivationNotDueError`, ORD-6) si se llama antes de tiempo.
- **Bloqueo post-expiración**: `accept_customer_adjustment()`/`reject_customer_adjustment()`
  ahora rechazan con `CustomerApprovalExpiredError` si `customer_approval_status ==
  EXPIRED` — una decisión tardía del cliente no revive una aprobación ya vencida.
- `ExpireCustomerApprovalUseCase` — mismo patrón que `ActivateScheduledOrderUseCase`
  (ORD-6): `now` inyectado, reutiliza `CUSTOMER_APPROVAL_OVERRIDE` (disparador de
  sistema/scheduler, no una acción de usuario final distinta).

## Decisiones

- **"WhatsApp" (§27, primer punto de la lista de ORD-11) NO se construyó** — requiere el
  gateway de notificaciones real (`WhatsAppOrderNotifier`, ORD-23) y el dispatcher de
  outbox (ORD-24), ninguno de los dos existe todavía. El evento
  `CUSTOMER_APPROVAL_REQUIRED` ya se encola correctamente desde ORD-10; falta el
  consumidor que lo convierta en un mensaje real. Documentado como pendiente explícito,
  coherente con la secuencia recomendada en ORD-0 (WhatsApp real es ORD-23).
- **No se repitió trabajo de ORD-10** — Aceptación/Rechazo ya existían; esta fase solo
  agregó lo que genuinamente faltaba (idempotencia, expiración), evitando duplicar
  `AcceptWeightAdjustmentUseCase`/`RejectWeightAdjustmentUseCase`.

## Tests

11 tests nuevos (8 dominio + 3 integración, esta última con el pipeline completo hasta
expiración). Suite acumulada ORD-1..11: **162/162 pasando**.

## Pendiente

- Notificación real por WhatsApp (ORD-23) y su disparo automático vía outbox (ORD-24).
- Un disparador periódico real que llame `ExpireCustomerApprovalUseCase` en el momento
  correcto no existe todavía (mismo pendiente que la activación de programados, ORD-6).
