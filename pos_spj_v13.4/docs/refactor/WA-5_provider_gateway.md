# WA-5 — Provider Gateway (canal WhatsApp)

Ejecutado: 2026-09-01. `infrastructure/providers/meta_cloud_api/gateway.py::MetaCloudApiWhatsAppGateway`
— implementación concreta de `domain/whatsapp/provider_ports.py::WhatsAppProviderGateway`
(el `Protocol` que WA-2 ya había definido). Wireada en el `WhatsAppCompositionRoot`
(WA-4) y en el health check en vivo de `main.py`.

---

## 1. Corrección a WA-2 — el Protocol necesitaba ser async

`provider_ports.py` (WA-2) declaraba los métodos como `def` síncronos. Al
implementarlos de verdad se hizo evidente que eso no encajaba: el único
sender real y en producción (`messaging/sender.py`) ya es 100% async sobre
`httpx.AsyncClient`, y todo lo que llamará a este puerto (webhook, flows)
también lo es. Se corrigió el `Protocol` — todos los métodos que hablan con
la Graph API pasaron a `async def`. `health_check()` es la única excepción
deliberada: sigue síncrono porque `bootstrap/health_checks.py` (WA-4) es un
agregador síncrono y un ping de salud liviano no justificaba volver async
todo ese módulo. Ningún consumidor real existía todavía para este Protocol
(la propia tabla de WA-4 lo marcaba "pendiente"), así que corregirlo no
rompió nada.

## 2. No es un segundo sender (§2/§81)

El propio inventario de WA-0 ya había señalado como duplicidad real: "2
implementaciones de envío: `core/services/whatsapp_service.py` +
`messaging/sender.py`". Construir un tercer camino de envío dentro del
gateway habría empeorado exactamente ese problema. En vez de eso:

- Se extrajo `messaging/sender.py::_post_message()` — el único punto que
  realmente hace `httpx.AsyncClient().post(...)` contra la Graph API para
  enviar. Antes esa llamada HTTP estaba duplicada inline dentro de
  `send_message` y `send_template`; ahora ambas funciones (sin cambiar su
  contrato público `bool`, verificado con los tests existentes de WA-1/CRM-31
  que ya pasaban) y el nuevo gateway pasan por la misma función.
- El gateway reutiliza además las mismas piezas de configuración/
  consentimiento/redacción que `sender.py` ya tenía: `_get_whatsapp_config`
  (resolución BD→`whatsapp_numeros`→env), `_is_whatsapp_opted_out` (CRM-31),
  `_normalize_phone`, `redact_phone` (WA-1). Nada de esto se reimplementó.

## 3. Los 8 métodos del Protocol

| Método | Cómo |
|---|---|
| `send_text` | Arma payload `type: text`, delega en `_send_payload` (config + opt-out + `_post_message`) |
| `send_template` | Igual, con parámetros de `template.components[0].parameters` **posicionales** — Meta no acepta nombrados; usa el orden de inserción del dict que el llamador pase |
| `send_interactive` | Envuelve el objeto `interactive` que el llamador ya construyó (botones/listas siguen siendo responsabilidad de la capa conversacional, hoy `messaging/interactive.py`) — el gateway no construye UI, solo transporta |
| `send_media` | Nuevo — soporta los 5 tipos de Meta (image/audio/video/document/sticker); decide `link` vs `id` según si `media_reference` empieza con `http` |
| `mark_read` | Nuevo — `POST` con `status: read` |
| `download_media` | Nuevo — descarga en 2 pasos como exige la Graph API (§62): `GET /{media_id}` → URL firmada temporal → `GET` esa URL |
| `get_message_status` | **Siempre retorna `None`, a propósito** — ver §4 |
| `health_check` | Nuevo — `GET /{phone_number_id}` (no existe un endpoint de "ping" dedicado en la Graph API; esta es la consulta más barata que igual valida auth+conectividad reales) |

## 4. `get_message_status` — limitación real de la API, no una omisión

Meta Cloud API **no expone ningún endpoint para consultar el estado de un
mensaje por su ID**. Los estados (`sent`/`delivered`/`read`/`failed`) solo
llegan como eventos de webhook (`statuses` dentro del payload de `POST
/webhook`). El método existe porque §22 del prompt maestro lo pide
explícitamente en la interfaz, pero la implementación real siempre
retorna `None`, con un docstring explícito citando esta limitación —
fingir un polling que la API no soporta habría sido peor que no
implementarlo. El estado real se procesará donde realmente llega: el
webhook, en WA-6, actualizando `WhatsAppMessageDelivery` (WA-2/WA-3)
directamente.

## 5. Integración en CompositionRoot y health check (WA-4)

- `WhatsAppCompositionRoot` registra `PROVIDER_GATEWAY` = una instancia de
  `MetaCloudApiWhatsAppGateway()`, ahora parte de `REQUIRED_SERVICES` (9,
  antes 8) — verificado por el mismo `dependency_graph_validator` de WA-4.
  La tabla de "pendientes" del docstring del módulo perdió su fila
  `ProviderGateway`.
- `bootstrap/health_checks.py::check_provider_gateway` reemplaza el
  placeholder `UNKNOWN` fijo de WA-4 por un ping real. Diseño deliberado
  para no duplicar severidad: si los secretos de Meta no están
  configurados, `check_secrets` ya lo reporta (DEGRADED fuera de
  producción, UNHEALTHY en producción) — este check no repite esa misma
  señal, reporta `UNKNOWN` con una nota. Solo pasa a `UNHEALTHY` cuando los
  secretos SÍ están configurados pero el ping real igual falla (token
  revocado, `phone_number_id` incorrecto) — una señal genuinamente nueva
  que ningún otro check detecta. Verificado con smoke test real contra
  `main.py` (ver Tests).

---

## Tests

67 tests nuevos/tocados, todos en verde:

- `test_sender_post_message.py` (6) — `_post_message` en sus 6 escenarios
  (éxito con/sin `messages[]`, no-200, timeout normalizado, excepción
  inesperada normalizada, JSON malformado en un 200).
- `test_meta_cloud_api_gateway.py` (23) — cada uno de los 8 métodos,
  incluidos los casos de guardia compartidos con `sender.py` (opt-out
  bloquea antes de llamar `_post_message`, teléfono inválido nunca llega a
  red, config ausente nunca llega a red), la construcción posicional de
  parámetros de template, media `link` vs `id`, y `download_media`/
  `health_check` con clientes `httpx` falsos (sin red real).
- `test_composition_root.py` (+1) — `provider_gateway` accessor.
- `test_health_checks.py` (actualizado) — reemplazó el test de placeholder
  `UNKNOWN` fijo por 4 tests del check real (sin configurar → `UNKNOWN`,
  configurado+ping ok → `HEALTHY`, configurado+ping falla → `UNHEALTHY`,
  y explícitamente que NO duplica la severidad de `check_secrets`).
- `test_sender_consent_gate.py`/`test_templates_parameter_validation.py` —
  re-ejecutados sin cambios para confirmar que el refactor de
  `send_message`/`send_template` (extracción de `_post_message`) no alteró
  su contrato público.

Suite completa `whatsapp_service/tests/`: **307 passed, 11 failed** — los
11 son los mismos fallos preexistentes y no relacionados ya documentados
desde WA-1. Sintaxis global: sin errores. Smoke test real (`TestClient`
contra `main.py`, base bootstrapeada desde cero): `/health` responde 200,
`provider_gateway` reporta `UNKNOWN` con `"sin configurar — ver check
'secrets'"` (no `UNHEALTHY` duplicado) — confirma que la integración con
WA-4 funciona en el proceso real, no solo en tests aislados.

## Siguiente fase

WA-6 — Webhook: verificación, firma (ya cubierto en WA-1), dedupe, inbox,
worker asíncrono. Es la fase que finalmente le da un consumidor real a
`get_message_status`'s ausencia (procesando `statuses` del webhook
directamente) y a `whatsapp_inbox` (WA-3, todavía sin productor). La
decisión de producto pendiente desde WA-0 (pipeline de pedidos
autoritativa) sigue sin bloquear nada — tampoco bloqueará WA-6.
