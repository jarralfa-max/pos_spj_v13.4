# SDLC-PAY-025 — Pago remoto por WhatsApp/CRM: enlace inalcanzable, preferencias repetidas y estado financiero en el microservicio

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 14 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 14 «Flujo de enlace alcanzable» (`defectuoso`), «Un solo intento por pedido» (`ausente`), «Estado de pago consultable por CRM» (`parcial`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-014, SDLC-WA-003, SDLC-ORD-003

## Problema
`PagoFlow.iniciar_pago` no tiene llamadores: el flujo de pedido promete el enlace y vuelve a reposo. Cuando se genera un enlace, cada clic crea una preferencia nueva. El microservicio escribe el estado financiero en tablas del ERP. CRM lee la tabla legacy de pedidos de WhatsApp y no tiene contrato de estado de pago; los casos de uso de pago de pedidos sólo corren en pruebas.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `whatsapp_service/flows/pago_flow.py:32,46-47`; `whatsapp_service/flows/pedido_flow.py:319-331`
- `whatsapp_service/router/notify_router.py:76-81`
- `whatsapp_service/erp/gateways/payment_gateway.py:23-55`; `whatsapp_service/erp/bridge.py:752-771,899-931`
- `backend/application/orders_delivery/use_cases/sales_finance_use_cases.py:122-184` (sólo pruebas)
- `backend/application/customers/queries/customer_orders_summary_query.py:49`
- Prueba: `tests/integration/test_orders_delivery_sales_finance_use_cases.py`

## Impacto
Clientes remotos sin forma de pagar; riesgo de cobro duplicado entre canales.

## Objetivo
- Flujo: crear pedido → total con políticas → orden MP (PAY-014) → enlace enviado por el servicio de mensajería existente → evento → validación por API → confirmar pedido → notificar → logística.
- El microservicio no es dueño del estado financiero; consume contratos del ERP.
- Un solo intento de pago activo por pedido entre canales.
- CRM consulta el estado de pago por un contrato de aplicación autorizado.

## Alcance
- **Incluye:** Flujos del microservicio, contrato ERP, consulta CRM, pruebas.
- **No incluye:** Anticipos y su asiento (SDLC-WA-004); escrituras SQLite del bridge (SDLC-WA-007).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-WA-001/003/004/006/007, SDLC-ORD-003.

## Preguntas abiertas
- Ninguna por ahora.

## Ampliación 2026-11-01 (`/sdlc-plan arquitectura docs/sdlc/inputs/whatsapp.md`)
Origen: `docs/sdlc/inputs/whatsapp.md` §38; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`.
- Re-verificado: `whatsapp_service/flows/pedido_flow.py:319-323` sigue prometiendo "Te enviaremos el link de pago" (*verificado directamente*) y `PagoFlow.iniciar_pago` sigue sin llamadores; los flujos se construyen sin orquestador (`whatsapp_service/router/message_router.py:189-195`).
- Relacionados: SDLC-WA-004 (anticipo nunca registrado), SDLC-WA-021 (precio de registro).
