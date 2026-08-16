# CRM-31 — WhatsApp: el consentimiento del Customer Master ahora bloquea envíos reales

Fecha: 2026-08-16. Cuarta fase del cut-over completo (mapa Fase 0
§WhatsApp/consent). CRM-30 (Delivery/Loyalty) se investigó primero y se
determinó de bajo valor inmediato — ver sección final.

## Hallazgo

El dominio de privacidad/consentimiento (`backend/domain/customer_privacy/`,
CRM-9) existe completo — `CustomerConsent` con captura/confirmación/retiro,
`CustomerConsentQueryService.is_active()` documentado explícitamente como
"la forma sancionada de chequear... antes de enviar un mensaje de
WhatsApp/marketing" — pero **nunca estuvo conectado a ningún envío real**.
`whatsapp_service/messaging/sender.py` (el punto de envío real hacia la
API de Meta) no tenía ningún chequeo de consentimiento; grep de
consent/opt_in/opt_out en todo el microservicio no arrojaba resultados.

Un docstring existente (`customer_whatsapp_summary_query.py`, lado CRM)
ya documentaba esto como un hueco deliberado, asumiendo que conectar el
gate real requeriría "una llamada REST a `whatsapp_service/erp/bridge.py`,
que no existe todavía". Investigando `erp/bridge.py` se encontró que esa
asunción ya no aplica: CRM-25 estableció un patrón probado
(`_bridge_customer_to_crm`) para importar el paquete `backend` del ERP
directamente desde `whatsapp_service` vía `sys.path`, condicionado a que
el checkout compartido exista — ambos servicios corren sobre el mismo
archivo SQLite. No hace falta ningún endpoint REST nuevo.

## Diseño (por qué NO es un bloqueo estricto por ausencia)

Auditoría confirmó: hoy no existe ningún productor de registros de
consentimiento reales en todo el sistema — el dominio se construyó en
CRM-9 pero nada lo alimenta todavía. Un gate que exigiera "WHATSAPP debe
estar GRANTED" habría bloqueado **el 100% de los envíos actuales**
(confirmaciones de pedido, avisos de entrega, etc.) desde el día uno —
exactamente el tipo de regresión de control que CRM-25 ya evitó para el
gate de crédito.

Por eso el gate implementado es asimétrico, igual que exige §44 ("no
inferir consentimiento" aplica en ambos sentidos): **solo bloquea si
existe un registro WHATSAPP explícitamente `WITHDRAWN`** para el cliente
resuelto. Ausencia de registro, `GRANTED`, `PENDING` o `NOT_REQUIRED` —
todos dejan pasar el envío exactamente como hoy. Es un gate real, no
decorativo, listo para el día en que exista un flujo de captura de
opt-out (fuera de alcance de esta fase — no se fabricó uno falso).

## Qué se construyó

- `whatsapp_service/messaging/sender.py::_is_whatsapp_opted_out(phone)`:
  resuelve `clientes` (por teléfono, reutilizando
  `ERPBridge.find_cliente_by_phone`) → `customers` (bridge CRM-21) →
  última fila de `customer_consents` tipo WHATSAPP. Defensivo por
  completo (mismo criterio que `_bridge_customer_to_crm`): cualquier
  fallo — cliente no encontrado, paquete ERP no importable, DB no
  disponible — degrada a "no retirado", nunca bloquea un envío por una
  falla de plomería.
- `send_message()` y `send_template()` (los dos puntos de envío reales;
  `send_text`/`send_buttons`/`send_list` delegan a `send_message` así que
  quedan cubiertos transitivamente) llaman el gate antes de tocar la API
  de Meta.

## Explícitamente NO tocado en esta fase

- Ningún flujo de captura de opt-in/opt-out — no existía antes, sigue sin
  existir; esta fase conecta el gate de lectura, no construye el
  productor.
- Requerir consentimiento MARKETING para notificaciones transaccionales
  (confirmación de pedido, entrega en camino) — estas siguen enviándose
  sin exigir opt-in, correcto: son comunicación transaccional de un
  pedido que el cliente ya inició, no marketing.
- Cambiar el teléfono usado para enviar (`clientes.telefono` /
  `delivery_orders.cliente_tel`) al `phone_e164` canónico del Customer
  Master — el gate opera sobre el teléfono ya usado hoy; migrar la fuente
  del teléfono es un cambio más amplio, no bloqueante para este gate.

## CRM-30 (Delivery/Loyalty) — investigado, sin cambios de código

La auditoría original marcó Delivery/Loyalty como "totalmente legacy",
pero al investigar se confirmó que su lado de LECTURA ya está
correctamente integrado: `Customer360QueryService` ya envuelve
`CustomerDeliverySummaryQuery` y `LoyaltyCustomerSummaryQuery`
(CRM-13), ambas wireadas de punta a punta hasta
`customer_profile_page.py` (los labels `loyalty_enrolled`/
`loyalty_points`/`loyalty_tier` ya se pueblan desde ahí). No hay ningún
workflow moderno desconectado ahí, a diferencia de crédito (CRM-27) o
consentimiento (esta fase). Lo que sigue legacy es el lado de
ESCRITURA (`delivery_orders.cliente_id`, `loyalty_ledger.cliente_id`,
etc.) — migrarlo requiere trabajo de UI nuevo (selector de dirección
canónica en creación de pedido, por ejemplo), no una reconexión de bajo
riesgo como las demás fases — se documenta como deuda real, no se
improvisa a medias.

## Verificación

```bash
cd whatsapp_service && python -m pytest tests/test_sender_consent_gate.py -v
```
5 tests nuevos, todos pasando.

```bash
cd whatsapp_service && python -m pytest tests/ -q \
  --ignore=tests/test_adjustment_approval_phase7.py \
  --ignore=tests/test_ai_fallback_mapping.py \
  --ignore=tests/test_cotizacion_flow_phase6.py \
  --ignore=tests/test_intent_resolver.py \
  --ignore=tests/test_intent_resolver_ai_paths.py \
  --ignore=tests/test_message_router_branch_switch.py \
  --ignore=tests/test_message_router_intent_resolver_integration.py
```
16 passed, 1 fallo preexistente confirmado no relacionado
(`test_conversation_quote_context.py` — `PermissionError` de Windows al
limpiar un `tempfile.TemporaryDirectory()` con un handle SQLite todavía
abierto; falla idéntico en aislamiento total, sin tocar nada de
mensajería/consentimiento). Los 7 archivos ignorados tienen una colisión
de `sys.path` preexistente y documentada (`config.py` del ERP vs
`config/` de whatsapp_service) — no relacionada con esta fase.
