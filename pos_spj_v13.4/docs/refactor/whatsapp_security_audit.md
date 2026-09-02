# Auditoría de seguridad — Canal WhatsApp (FASE CERO — Auditoría)

Manejo de secretos, verificación de firmas de webhook, protección contra replay, autenticación
interna ERP↔microservicio, redacción de logs, y manejo de excepciones. Ningún valor de secreto real
se imprime en este documento — solo `file:línea` y, cuando aplica, el patrón de enmascarado ya
existente en el código.

---

## 1. Dónde viven los secretos hoy

| Secreto | Fuente primaria | Fuente de respaldo | Archivo:línea |
|---|---|---|---|
| `WA_ACCESS_TOKEN` / Meta token | `configuraciones.wa_meta_token` (BD ERP) | env `WA_ACCESS_TOKEN` | `whatsapp_service/config/settings.py:79-86` (`get_meta_access_token`) |
| `WA_PHONE_NUMBER_ID` | `configuraciones.wa_meta_phone_id` (BD ERP) | env `WA_PHONE_NUMBER_ID` | ídem, `:79-81` |
| `WA_VERIFY_TOKEN` | `configuraciones.wa_verify_token` (BD ERP) | env `WA_VERIFY_TOKEN` | `settings.py:89-96` |
| `WA_APP_SECRET` (firma HMAC Meta) | solo env | — | `settings.py:39`, sin lectura desde BD (a diferencia de los otros 3) |
| `WA_INTERNAL_API_KEY` (canal ERP↔microservicio) | `configuraciones.wa_internal_api_key` (BD ERP) | env `WA_INTERNAL_API_KEY`/`INTERNAL_API_KEY` | `settings.py:98-104` |
| `MP_ACCESS_TOKEN` / `MP_WEBHOOK_SECRET` | solo env | — | `settings.py:127-128` |
| Meta/Twilio token (lado UI admin) | `whatsapp_numeros.meta_token`/`twilio_token` (BD ERP) | — | `core/repositories/whatsapp_config_repository.py:65-93` |

**Hallazgo 1 — no hay `SecretStore` dedicado.** Cada lectura de secreto vuelve a abrir una conexión
SQLite nueva contra la BD del ERP (`sqlite3.connect(db_path)` dentro de `_read_erp_config()`,
`settings.py:54-76`, sin caching ni TTL) — se ejecuta en cada llamada a `send_message`
(`messaging/sender.py:_get_whatsapp_config`, líneas 56-108) y en cada webhook `GET`/`POST` recibido
(`get_verify_token()` en `webhook/whatsapp.py:45-47`). El "SecretStore" que pide el prompt maestro no
existe; hoy es "leer la tabla `configuraciones` cada vez, con `.env` como respaldo técnico" — funcional
pero sin control de acceso, auditoría de lectura, ni rotación automática.

**Hallazgo 2 — inconsistencia de fuente por secreto.** `WA_APP_SECRET` y `MP_WEBHOOK_SECRET`
**solo** se leen de variables de entorno (no tienen el mismo patrón "BD primero, env después" que los
demás) — significa que si un operador configura todo desde la UI (`ModuloWhatsApp` →
`CredentialsPanel`) pero no toca el `.env`, la firma de Meta (`WA_APP_SECRET`) y de MercadoPago
(`MP_WEBHOOK_SECRET`) quedarán vacías, y ambos webhooks caen a **fail-open** (ver §2).

**Hallazgo 3 — enmascarado de credenciales solo en un lugar.**
`core/services/whatsapp_credential_service.py:_mask_token()` (líneas 62-66) es la única función que
enmascara tokens (`token[:4] + "***" + token[-4:]`) para mostrarlos en UI
(`get_masked_credentials`, líneas 50-60). El microservicio (`whatsapp_service/`) no tiene equivalente
— sus logs de error (por ejemplo `messaging/sender.py:206-207`, `resp.text[:500]`) podrían incluir
fragmentos de la respuesta de la API de Meta, que en teoría no debería traer el token de vuelta, pero
no hay ninguna redacción explícita si algo cambia en el futuro.

---

## 2. Verificación de firma de webhook — inconsistente entre proveedores y fail-open por diseño

| Webhook | Mecanismo | Fail-open si falta config | Archivo:línea |
|---|---|---|---|
| Meta — verificación inicial (`GET /webhook`) | Compara `hub.verify_token` con `get_verify_token()` usando `hmac.compare_digest` (bien: constante en tiempo) | Devuelve 503 si no hay verify token configurado (no fail-open) | `whatsapp_service/webhook/whatsapp.py:32-60` |
| Meta — mensajes entrantes (`POST /webhook`) | `verify_signature()` = HMAC-SHA256 sobre el body con `WA_APP_SECRET`, header `X-Hub-Signature-256` | **Sí** — si `WA_APP_SECRET` está vacío, el `if WA_APP_SECRET:` en la línea 68 simplemente **omite** la verificación y procesa el mensaje igual | `whatsapp_service/webhook/whatsapp.py:65-72` |
| MercadoPago (`POST /webhook/mercadopago`) | `verify_mp_signature()` = HMAC-SHA256 sobre un manifest `id:...;request-id:...;ts:...;` con `MP_WEBHOOK_SECRET` | **Sí** — si `MP_WEBHOOK_SECRET` está vacío, solo se loguea un `warning` y se procesa el pago igual (líneas 41-45) | `whatsapp_service/webhook/mercadopago.py:34-45` |
| Webhook legacy Meta (`WhatsAppWebhookServer`, puerto 8767) | **Ninguna verificación de firma.** `WebhookHandler.do_POST()` lee el body y lo procesa directamente; solo `do_GET()` compara el verify_token, y con `==` plano (no `compare_digest`) | Siempre fail-open (no hay ningún secreto que verificar en `POST`) | `pos_spj_v13.4/core/services/whatsapp_service.py:490-497` (POST), `:480-488` (GET, comparación `vt == exp`) |

**Implicación operativa**: la seguridad real del canal depende hoy 100% de que los operadores
efectivamente hayan configurado `WA_APP_SECRET` y `MP_WEBHOOK_SECRET` — el código no lo exige, solo lo
"honra si está". No hay ningún chequeo de arranque (`main.py` lifespan, `whatsapp_service/main.py:66-149`)
que aborte o alerte si el microservicio arranca en modo producción sin esos dos secretos configurados
— contrasta con el patrón mucho más estricto que sí existe para *escrituras* SQLite
(`is_production()` + `_assert_sqlite_write_allowed`, `erp/bridge.py:208-213`). Es decir: el proyecto
ya tiene el patrón "bloquear en producción si falta configuración crítica" implementado para un tipo
de riesgo (fallback SQLite) pero no lo aplicó al riesgo de verificación de firma de webhook.

**Hallazgo adicional — replay**: ninguna de las dos verificaciones de firma (Meta ni MercadoPago)
comprueba una ventana de tiempo (`ts`) contra el reloj del servidor para descartar mensajes viejos
reenviados; `verify_mp_signature()` extrae `ts` del header pero solo lo usa como parte del manifest a
firmar, no lo compara contra `now()` con una tolerancia — un firma HMAC válida pero vieja (capturada y
reenviada) pasaría la verificación igual. La única protección contra reprocesamiento es el dedupe por
`message_id`/`action_key` descrito en `whatsapp_event_inventory.md`, que protege contra duplicados
*procesados por este sistema*, no contra un atacante reproduciendo una petición firmada válida dentro
de la ventana antes de que se dedupe.

---

## 3. Autenticación interna ERP↔microservicio — no es HMAC, es comparación de string plano, y está duplicada

El prompt maestro pide "HMAC internal auth" para el canal interno. Lo que existe hoy:

- `whatsapp_service/middleware/auth.py:require_internal_key()` (líneas 7-20) — comparación
  `x_internal_key != internal_key` (string plano, no `hmac.compare_digest`, vulnerable a timing
  attack de baja severidad dado que es un canal interno). **Este código está muerto**: no está
  registrado como `Depends()` en ningún router (confirmado por grep — cero referencias fuera de su
  propia definición).
- En su lugar, cada router reimplementa su propia copia del mismo patrón:
  - `whatsapp_service/router/notify_router.py:_check_internal_key()` (líneas 36-47)
  - `whatsapp_service/router/delivery_router.py:_check_internal_key()` (líneas 56-62, mismo patrón)

  Ambas comparan también con `!=` (no `hmac.compare_digest`), y ambas son **fail-open**: si
  `get_internal_api_key()` devuelve cadena vacía (porque no se configuró ni en BD ni en env), el
  chequeo se salta por completo con solo un `logger.warning` (`notify_router.py:39-44`,
  `"Internal API key not configured — notify endpoints are unprotected... Dev mode: allow through
  with warning"`). Es decir, **por defecto, sin configuración explícita, los endpoints
  `/api/notify/*` y de delivery quedan abiertos sin autenticación** a cualquiera que pueda alcanzar
  el puerto 8000.
- `middleware/hmac_validator.py` (la única implementación HMAC real del repo) se usa exclusivamente
  para firmas de proveedor externo (Meta, MercadoPago) — **nunca** para el canal interno ERP↔WA. El
  canal interno que el prompt maestro pide asegurar con HMAC sigue usando comparación de secreto
  compartido plano.

**Resumen de la brecha**: existe la primitiva correcta (`hmac_validator.py`) pero no está aplicada al
lugar que el prompt maestro identifica como el que más lo necesita (autenticación de servicio a
servicio), y la única implementación de auth interna que sí existe (`middleware/auth.py`) es código
muerto duplicado tres veces con lógica ligeramente distinta cada vez.

---

## 4. Redacción de logs y manejo de excepciones

- **Enmascarado de teléfono, parcial**: algunos logs truncan el teléfono
  (`core/delivery/infrastructure/whatsapp_delivery_notifier.py:145`, `phone[-4:]`;
  `whatsapp_service/erp/pos_notifier.py` no revisado en este punto específico), pero otros lo
  loguean completo (`whatsapp_service/webhook/whatsapp.py:71`, `request.client.host` — no es el
  teléfono pero sí la IP del cliente/proxy de Meta; `messaging/sender.py:203`,
  `_normalize_phone(msg.to)` completo en el log de éxito). No es un secreto per se (el teléfono ya
  es visible en la conversación), pero es dato personal — no hay una política uniforme de
  redacción en todo el árbol.
- **`except Exception: pass` / `except Exception as e: logger.debug(...)` extendido**: 56
  ocurrencias en 23 archivos de `whatsapp_service/` (conteo por grep). La mayoría son defensivos
  y razonables (ej. `sender.py` catch de `httpx.TimeoutException`), pero al menos dos casos
  **enmascaran errores de integridad de datos silenciosamente**:
  - `whatsapp_service/erp/events.py:126-128` — el `INSERT INTO wa_event_log` que falla
    sistemáticamente por incompatibilidad de esquema (ver `whatsapp_schema_consolidation.md`)
    queda atrapado por un `except Exception: pass` desnudo, sin siquiera loguear a nivel `debug`.
    Esto significa que el audit trail de eventos WhatsApp (`wa_event_log`), que el propio
    CLAUDE.md del proyecto exige para toda operación con impacto financiero (regla 12,
    *"toda operación financiera debe loguear en `financial_event_log`"* — análogo aquí sería
    `wa_event_log` para trazabilidad del canal), **no se está persistiendo en producción** sin que
    absolutamente nada lo señale.
  - `whatsapp_service/erp/pos_notifier.py:184-185` — mismo patrón, pero al menos loguea a nivel
    `debug` (`logger.debug("No se pudo insertar wa_event_log %s: %s", event_type, exc)`) — invisible
    con la configuración de logging por defecto (`LOG_LEVEL=INFO`, `config/settings.py:142`).

---

## 5. Consentimiento / opt-out

- **Único gate real encontrado**: `whatsapp_service/messaging/sender.py:_is_whatsapp_opted_out()`
  (líneas 125-169), etiquetado explícitamente "CRM-31". Consulta
  `customer_consents WHERE customer_id=? AND consent_type='WHATSAPP' ORDER BY created_at DESC LIMIT 1`
  y bloquea el envío solo si el último estado es `'WITHDRAWN'`. El propio docstring del método
  (líneas 126-139) es honesto sobre el estado real: *"hoy no existe ningún productor de estos
  registros en el sistema... en la práctica esto siempre retorna False hasta que exista un flujo de
  captura de opt-out"*. Es decir, el gate está bien escrito (falla seguro hacia "no bloquear" ante
  cualquier error de plomería, líneas 166-169) pero **no tiene ningún productor de datos** — nadie en
  el repo hoy escribe una fila `WITHDRAWN` en `customer_consents` para el canal WhatsApp.
- Este gate solo se invoca desde `send_message`/`send_template` del microservicio oficial
  (`sender.py:183-185`, `:256-258`). **No existe** el mismo chequeo en el camino de envío legacy
  (`core/services/whatsapp_service.py:_send_meta`/`_send_twilio`, líneas 436-459) — cualquier
  notificación que salga por la cola legacy (§2b de `whatsapp_runtime_map.md`, que es tráfico real de
  producción hoy) **no respeta el opt-out** aunque el cliente lo hubiera registrado.

---

## 6. Resumen de hallazgos priorizados

| # | Hallazgo | Severidad | Archivo:línea |
|---|---|---|---|
| S1 | Endpoints `/api/notify/*` y `/api/delivery/*` quedan sin autenticación si `WA_INTERNAL_API_KEY` no está configurado (fail-open, solo warning) | Alta | `router/notify_router.py:39-47`, `router/delivery_router.py:56-62` |
| S2 | Autenticación interna es comparación de string plano, no HMAC, contradiciendo el requisito del prompt maestro; la única función HMAC del repo nunca se usa para esto | Alta | `middleware/hmac_validator.py` (no usado aquí) vs `router/notify_router.py`/`delivery_router.py` |
| S3 | `middleware/auth.py:require_internal_key` es código muerto duplicado 2 veces con variaciones | Media | `middleware/auth.py:7-20` |
| S4 | Verificación de firma Meta y MercadoPago es fail-open si el secreto no está configurado, sin gate de arranque que lo exija en producción | Alta | `webhook/whatsapp.py:68-72`, `webhook/mercadopago.py:34-45` |
| S5 | Webhook legacy (puerto 8767) no verifica firma en absoluto y usa comparación no constante en el verify_token | Alta (dado que el servidor está activo por defecto, ver runtime map) | `core/services/whatsapp_service.py:480-497` |
| S6 | Audit trail `wa_event_log` no se persiste en producción por incompatibilidad de esquema, silenciado por `except: pass` | **Crítica** (viola la regla 12 del CLAUDE.md del proyecto sobre trazabilidad) | `erp/events.py:110-128` |
| S7 | Gate de consentimiento/opt-out (CRM-31) no tiene productor de datos y no cubre el camino de envío legacy | Media-Alta | `messaging/sender.py:125-169` (sin cobertura), `core/services/whatsapp_service.py:436-459` (sin gate) |
| S8 | No hay `SecretStore` centralizado; cada lectura de secreto reabre SQLite sin cache; `WA_APP_SECRET`/`MP_WEBHOOK_SECRET` no siguen el mismo patrón BD+env que el resto | Media | `config/settings.py:22-172` |
| S9 | Sin protección de replay por ventana de tiempo en ninguna de las dos firmas HMAC de proveedor | Media | `middleware/hmac_validator.py:8-42` |
