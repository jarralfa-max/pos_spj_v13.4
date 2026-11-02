# SDLC-WA-003 — Pedidos, cotizaciones y anticipos por WhatsApp no pueden crearse en producción

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-002

## Problema
El bridge llama endpoints REST (`/api/v1/clientes`, `/pedidos`, `/cotizaciones`, `/anticipos`, `/ordenes-compra`) que no existen en el ERP (sólo se montan logística, analítica, sync y dispositivos). En producción las escrituras SQLite están bloqueadas y la falla de API lanza: ningún pedido por WhatsApp puede crearse. Si la API respondiera, varios gateways no hacen `return` y además escriben `UPDATE ventas` por SQLite. El fallback SQLite inserta sin `id` en tablas con PK TEXT NOT NULL y usa `lastrowid` como identidad.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/api/main.py:23-25`, `backend/api/central_app.py:152-153` — routers montados *(verificado directamente en el triage)*
- `whatsapp_service/erp/bridge.py:213-225` — guardias de escritura *(verificado directamente en el triage)*
- `whatsapp_service/erp/gateways/delivery_gateway.py:13-31` — sin `return` tras el PATCH *(verificado directamente en el triage)*
- `whatsapp_service/erp/gateways/payment_gateway.py:24-55`, `whatsapp_service/flows/cotizacion_flow.py:198`
- `whatsapp_service/erp/bridge.py:279,314,442,474-492,679,701-706,756,767-771,804,910,973,998-1027`
- `migrations/m000_base_schema.py:580-581,607-608,689-690` — PK TEXT NOT NULL

## Impacto
El canal WhatsApp no puede vender en producción.

## Objetivo
- El bridge escribe a través de un contrato del ERP que existe (API o casos de uso canónicos), con un solo camino por operación.
- Ninguna escritura del microservicio toca tablas del ERP fuera de ese contrato.
- IDs UUIDv7 generados por el dueño del dato.

## Alcance
- **Incluye:** Contrato bridge↔ERP para clientes, pedidos, cotizaciones; gateways.
- **No incluye:** Anticipos/contabilidad (WA-004), cutover del webhook a WA-1..20 (decisión diferida por el usuario).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Microservicio WhatsApp: preservar los 3 shims de CLAUDE.md regla 9; el cutover del webhook a WA-1..20 sigue diferido por decisión del usuario.

## Trabajo previo relacionado
`docs/refactor/WA-22_validacion_final.md` (cutover pendiente); memoria WhatsApp; CLAUDE.md reglas 9 y 14.

## Preguntas abiertas
- ¿El destino es la API REST del ERP (aún inexistente) o los casos de uso canónicos `customer_orders`/`quotes`?
- ¿El canal WhatsApp está en uso hoy en alguna sucursal?

## Ampliación 2026-11-01 (`/sdlc-plan arquitectura docs/sdlc/inputs/whatsapp.md`)
Origen: `docs/sdlc/inputs/whatsapp.md` §34, §37, §52; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`.
- `ERPBridge.create` está definido dos veces (`whatsapp_service/erp/bridge.py:395` pedido y `:654` cotización, *verificado directamente*); gana el último, así que `ErpBridgeOrdersApiClient.create` (`whatsapp_service/infrastructure/erp_clients/erp_bridge_clients.py:86`) crearía una cotización o fallaría y `ErpBridgeQuotesApiClient.create` (`:113`) falla sin `sucursal_id`. La prueba lo oculta con `_FakeBridge.create(**kwargs)` (`whatsapp_service/tests/test_erp_bridge_clients.py:35`). Hoy es ruta no cableada.
- `whatsapp_service/application/confirm_order_use_case.py:61` hace `int(order["venta_id"])`: rompe con el UUID que devolvería la API.
- Dueños existentes sin API: `CreateCustomerOrderUseCase` (`backend/application/orders_delivery/use_cases/order_capture_use_cases.py:36`, deduplica por `whatsapp_order_id`/`operation_id`), `CaptureOrderUseCase` (`capture_order_use_cases.py:99`), casos de uso de Quotes (`backend/application/quotes/use_cases/quote_use_cases.py:129,333,343`). No existe `InventoryApiClient` ni fachada `ERPChannelGateway`; `consent_client.py:19-21` importa un repositorio interno del ERP y `loyalty_client.py:35` hace SQL directo.
- Se separaron en ítems propios: SDLC-WA-009 (autenticación WA→ERP), SDLC-WA-021 (precio de registro), SDLC-WA-028 (cotizaciones), SDLC-WA-031 (crédito), SDLC-WA-032 (delivery), SDLC-WA-033 (lealtad).
