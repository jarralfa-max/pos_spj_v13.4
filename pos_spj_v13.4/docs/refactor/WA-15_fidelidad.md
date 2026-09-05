# WA-15 — Fidelidad (canal WhatsApp)

Ejecutado: 2026-09-02. §8/§52 del prompt maestro.

## Qué se construyó

- `domain/whatsapp/erp_ports.py::LoyaltySummaryRef` — reemplaza el `Dict`
  crudo que `LoyaltyApiClient.get_summary()` tenía desde WA-9 (dejado sin
  implementar a propósito: "no existe ningún gateway de fidelidad real
  para envolver"). Ahora sí existe, así que se tipa igual que el resto de
  los `Ref` del módulo.
- `infrastructure/erp_clients/loyalty_client.py::LoyaltySnapshotApiClient`
  — primera implementación real de `LoyaltyApiClient`. Lee
  `loyalty_snapshots` — la MISMA tabla y forma de SQL que
  `LoyaltyCustomerSummaryQuery` (CRM-21, lado ERP). Deliberadamente NO
  reutiliza esa clase directamente: exige `actor_user_id` y pasa por
  `CustomerAuthorizationPolicy.require(..., LOYALTY_VIEW)` — un chequeo de
  "¿puede este EMPLEADO ver los puntos de este cliente?" que no aplica
  por WhatsApp (es el propio cliente consultando su propio saldo).
  Inventar un `actor_user_id` de sistema para pasar ese gate habría sido
  fingir una autorización que no existe; leer la misma tabla, sin ese
  gate, es la reutilización honesta.
- `application/loyalty_service.py::LoyaltyService.get_summary()` — capa
  fina, sin bridging de id (a diferencia de WA-14: `loyalty_snapshots.cliente_id`
  ya es el `clientes.id` legacy, el mismo que usan los demás clientes ERP
  de WA-9 — Fidelidad nunca migró a `customers.id`).

## Redención — corte de alcance explícito, verificado antes de decidir

Se investigaron los DOS `RedeemLoyaltyPointsUseCase` que existen en el
repo antes de decidir no construir redención por WhatsApp:

1. `backend/application/sales/use_cases/loyalty_use_cases.py::RedeemLoyaltyPointsUseCase`
   — el real, wireado en el checkout POS
   (`frontend/desktop/modules/sales_pos/composition.py`) y en Fidelidad
   (`frontend/desktop/modules/fidelidad/composition.py`). Acoplado a una
   venta EN CURSO (`sale_id`) — no es una acción independiente.
2. `backend/application/use_cases/redeem_loyalty_points_use_case.py::RedeemLoyaltyPointsUseCase`
   — un `DelegatingUseCase` sin `handler` inyectado en ningún punto del
   árbol (confirmado por grep) — un scaffold de Fase 6, no una
   implementación real.

Construir un tercer camino de redención sin `sale_id` habría significado
inventar lógica de negocio nueva (qué pasa con puntos canjeados sin una
venta que los respalde), exactamente el tipo de fuga que
`whatsapp_business_logic_leakage.md` (WA-0) ya documentó para otros
flujos. Se documenta el corte, mismo criterio que WA-12 con
`flows/pago_flow.py`.

CompositionRoot: +2 servicios (`loyalty`, `loyalty_service`) — degrada a
`UnavailableErpClient` si `loyalty_snapshots` no existe en la conexión.
`REQUIRED_SERVICES` pasó de 31 a 33.

## Tests

45 tests nuevos: `test_loyalty_client.py` (3), `test_loyalty_service.py`
(1), accessors de `CompositionRoot` (+3, incluida la variante con tabla
real).

Suite completa: **588 passed, 11 failed** (mismos preexistentes desde
WA-1).

## Siguiente fase

WA-16 (Handoff) — `middleware/handoff.py::HandoffService` ya hace trabajo
real (notifica staff + cliente) pero fuera de la arquitectura nueva; WA-16
construye el equivalente real dentro del bounded context, atado a la
señal `ConversationSignal.HANDOFF_REQUESTED` que WA-7/WA-8 ya definieron.
