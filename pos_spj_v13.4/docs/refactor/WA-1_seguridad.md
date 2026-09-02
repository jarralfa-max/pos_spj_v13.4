# WA-1 — Seguridad (canal WhatsApp)

Ejecutado: 2026-09-01. Remedia los hallazgos S1-S9 de `whatsapp_security_audit.md`
(FASE CERO / WA-0). Alcance: SecretStore, verificación de firma de webhooks
fail-closed en producción, autenticación interna HMAC + identidad de servicio,
redacción de logs, y el bug crítico de `wa_event_log`. No toca lógica de
negocio (leakage, tres pipelines paralelas) — eso es alcance de fases
posteriores (ver `whatsapp_legacy_inventory.md`, `whatsapp_business_logic_leakage.md`).

---

## 1. SecretStore

- Nuevo: `whatsapp_service/infrastructure/secrets/secret_store.py` —
  `SecretStore` centraliza la lectura de `configuraciones.wa_*` con cache TTL
  (30s) en vez de reabrir SQLite en cada request (Hallazgo 1), y expone
  `mask()` reutilizando el mismo patrón de enmascarado que
  `core/services/whatsapp_credential_service.py:_mask_token`.
- `whatsapp_service/config/settings.py`: se agregan `get_app_secret()` y
  `get_mp_webhook_secret()` con el mismo patrón "BD primero (`wa_app_secret`,
  `wa_mp_webhook_secret`), env después" que ya tenían las demás claves —
  cierra la inconsistencia de Hallazgo 2 (antes `WA_APP_SECRET` y
  `MP_WEBHOOK_SECRET` eran env-only). Todos los getters (`get_meta_access_token`,
  `get_meta_phone_number_id`, `get_verify_token`, `get_internal_api_key`,
  `get_app_secret`, `get_mp_webhook_secret`) ahora pasan por `SecretStore`
  para el cache, sin cambiar firma ni comportamiento de retorno — ningún
  caller existente necesitó cambios.

**Resuelve:** S8, Hallazgo 1, Hallazgo 2.

## 2. Webhooks — fail-closed en producción + replay en MercadoPago

- `webhook/whatsapp.py` y `webhook/mercadopago.py`: si `is_production()` y el
  secreto de firma (`WA_APP_SECRET` / `MP_WEBHOOK_SECRET`) no está
  configurado, la request se **rechaza** (503) en vez de procesarse sin
  verificar. Fuera de producción se mantiene el comportamiento anterior
  (warn + procesar) para desarrollo local.
- Nuevo gate de arranque en `whatsapp_service/main.py`:
  `_assert_production_secrets_configured()` — aborta el `lifespan` con
  `RuntimeError` si, en producción, falta cualquiera de
  `WA_ACCESS_TOKEN`/`WA_PHONE_NUMBER_ID`/`WA_VERIFY_TOKEN`/`WA_APP_SECRET`/
  `WA_INTERNAL_API_KEY` (y `MP_WEBHOOK_SECRET` cuando `MP_ACCESS_TOKEN` está
  configurado). Extraída como función standalone para ser testeable sin
  levantar FastAPI/DB/migraciones. Mismo criterio que ya existía para
  bloquear escrituras SQLite en producción (`erp/bridge.py::_assert_sqlite_write_allowed`),
  aplicado ahora también a este riesgo.
- `middleware/hmac_validator.py::verify_mp_signature()` acepta
  `max_age_seconds` (default 300) y rechaza una firma válida pero con `ts`
  fuera de esa ventana — cierra el hallazgo de replay para MercadoPago.
  **No** se aplicó lo mismo al webhook de Meta: `X-Hub-Signature-256` no
  lleva timestamp firmado, así que no hay forma sólida de acotar replay a
  nivel de firma ahí — la mitigación real sigue siendo el dedupe por
  `message_id` ya existente (`_conversation_store.is_duplicate`). Se dejó un
  comentario explícito en el código en vez de fingir una protección que no
  existe.

**Resuelve:** S4, S9. Reduce el riesgo operativo descrito en la "Implicación
operativa" del hallazgo §2 (ya no depende únicamente de que el operador haya
configurado los secretos — producción ahora lo exige para arrancar).

## 3. HMAC interno + identidad de servicio (reemplaza `X-Internal-Key` plano)

- Nuevo: `whatsapp_service/middleware/service_auth.py` — dependencia FastAPI
  `require_service_auth`: exige headers `X-Service-Id`, `X-Timestamp`,
  `X-Nonce`, `X-Signature` (más `X-Correlation-Id` para trazabilidad, no
  participa en la firma); valida tolerancia de reloj (120s), rechaza nonces
  repetidos (cache en memoria — un despliegue multi-worker necesitaría un
  store compartido, fuera de alcance de esta fase), y compara la firma HMAC
  con `hmac.compare_digest`. El secreto compartido sigue siendo
  `get_internal_api_key()` (mismo dato que antes); lo que cambia es que
  ahora se usa como clave HMAC, no como valor comparado con `!=`.
- `router/notify_router.py` y `router/delivery_router.py`: los endpoints
  `/api/notify/*` y `/api/delivery/*` (incluido `GET /orders/pending`, que
  antes no tenía ninguna protección pese a exponer teléfono/dirección/items)
  ahora dependen de `require_service_auth` en vez de reimplementar
  `_check_internal_key` con `!=` y fail-open silencioso.
- `middleware/auth.py` — **eliminado**. Era código muerto confirmado (cero
  `Depends()` en todo el árbol, reverificado antes de borrar): duplicaba mal
  el mismo patrón que los routers ya reimplementaban por su cuenta.
- `pos_spj_v13.4/core/integrations/whatsapp_client.py` (único llamador real
  de estos endpoints en todo el repo — `backend/infrastructure/integrations/orders_delivery_whatsapp_client.py`
  es un wrapper sobre este mismo cliente, no un segundo llamador) firma cada
  request con una copia corta y deliberadamente duplicada de la misma lógica
  de firma (documentada como debiendo mantenerse byte-a-byte compatible con
  `service_auth.py::sign_request` — verificado por test cruzado en ambos
  lados). Ya no envía `X-Internal-Key`.

**Resuelve:** S1, S2, S3.

## 4. Redacción

- Nuevo: `whatsapp_service/infrastructure/security/redaction.py` —
  `redact_phone()` (últimos 4 dígitos visibles) y `redact_secret()`
  (mismo patrón que `_mask_token`).
- Aplicado en `messaging/sender.py` donde se logueaba el teléfono normalizado
  completo en el log de envío exitoso.

**Resuelve:** parte de S8 (enmascarado antes solo existía en un lugar);
alcance intencionalmente acotado a lo señalado en el audit — una redacción
exhaustiva de todo el árbol es trabajo de observabilidad de una fase
posterior (WA-20).

## 5. Bug crítico — `wa_event_log` no se estaba insertando (S6)

Causa raíz: la migración 050 crea `wa_event_log` con `id TEXT NOT NULL
PRIMARY KEY` (sin default SQL — UUIDv7 obligatorio por REGLA CERO), pero
tres sitios distintos insertaban sin proveer `id`, y los tres estaban
protegidos por un `except: pass` o `except: logger.debug(...)` que
silenciaba el fallo por completo:

- `whatsapp_service/erp/events.py::WAEventEmitter.emit()`
- `whatsapp_service/erp/pos_notifier.py::_insert_wa_event()`
- `whatsapp_service/router/delivery_router.py::sync_order_status()` —
  encontrado de forma independiente durante esta fase (mismo bug raíz, no
  estaba nombrado explícitamente en el audit de WA-0).

Los tres ahora generan `id` con `new_uuid()` (`backend/shared/ids.py`, el
único generador UUIDv7 permitido por REGLA CERO) antes del INSERT. El
`ensure_tables()` de `events.py` y `pos_notifier.py` — que recreaban
`wa_event_log` con `id INTEGER PRIMARY KEY AUTOINCREMENT`, violando REGLA
CERO y desacordando con el esquema real de la migración — se corrigieron
para coincidir exactamente con la migración 050. Los `except` que
silenciaban el fallo ahora loguean a `WARNING` (visible con el
`LOG_LEVEL=INFO` por defecto) en vez de `pass`/`debug`.

**Resuelve:** S6 ("Crítica" — violaba la regla 12 de `CLAUDE.md` sobre
trazabilidad de auditoría). Regresión cubierta por
`whatsapp_service/tests/test_wa_event_log_insert.py`, que inserta contra un
esquema real (igual al de la migración 050) y verifica que la fila queda
persistida con un `id` UUIDv7 válido.

## 6. Fuera de alcance de esta fase (deferido explícitamente)

- **S7 — gate de consentimiento/opt-out.** El gate (`sender.py:_is_whatsapp_opted_out`,
  CRM-31) sigue sin ningún productor de datos, y el camino de envío legacy
  (`core/services/whatsapp_service.py:_send_meta`/`_send_twilio`) sigue sin
  cobertura. Esto requiere construir el flujo real de captura de opt-out
  (§45-46 del prompt maestro), que es trabajo de dominio/aplicación de una
  fase posterior (probablemente WA-14, Clientes y consentimiento), no
  hardening de infraestructura de seguridad. No tocado aquí.
- Business-logic leakage (`whatsapp_business_logic_leakage.md`) y la
  coexistencia de las tres pipelines de pedidos paralelas
  (`whatsapp_legacy_inventory.md`) — sin resolver, requieren una decisión de
  producto sobre cuál pipeline es la autoritativa antes de poder
  clasificarse DELETE/REWRITE. Ver los 5 ítems `BLOCKED` del inventario de
  WA-0.
- Un efecto colateral hallado durante la verificación (no un hallazgo de
  seguridad, corregido igualmente por diligencia al correr la suite
  completa): `whatsapp_service/messaging/templates.py::send_event_template`
  sustituía en silencio un parámetro de template faltante por cadena vacía
  en vez de negarse a enviar — ahora rechaza el envío y loguea el/los
  parámetro(s) faltante(s). Cubierto por el test preexistente
  `test_templates_parameter_validation.py`.

---

## Verificación

- `whatsapp_service/tests/` (con `PYTHONPATH` ordenado igual que
  `main.py` prioriza: `whatsapp_service` → `pos_spj_v13.4` → raíz del repo,
  necesario porque `pos_spj_v13.4/infrastructure/` y
  `whatsapp_service/infrastructure/` son paquetes top-level distintos con el
  mismo nombre — el mismo problema de ambigüedad que el propio `main.py` ya
  documenta para `application/`): **86 passed, 11 failed**. Los 11 fallos
  son preexistentes y no relacionados con esta fase (fixtures `DummyParser`
  sin atributo `.matcher` en tests de `intent_resolver`/`message_router` —
  ninguno de esos archivos fue tocado en WA-1). Los 62 tests nuevos/tocados
  por esta fase (`test_service_auth.py`, `test_secret_store.py`,
  `test_redaction.py`, `test_main_production_gate.py`,
  `test_webhook_production_fail_closed.py`, `test_wa_event_log_insert.py`,
  `test_mercadopago_webhook_signature.py`,
  `test_templates_parameter_validation.py`) pasan en su totalidad.
- `pos_spj_v13.4/tests/test_wa_client.py`: 9/9 passed (incluye 4 tests nuevos
  de firma HMAC del lado ERP).
- Sintaxis global (`ast.parse` sobre `pos_spj_v13.4/` y `whatsapp_service/`):
  sin errores.

**Nota operativa para producción:** con este cambio, el microservicio ya
**no arranca** en `APP_ENV=production` si faltan `WA_APP_SECRET`,
`WA_INTERNAL_API_KEY`, o cualquiera de los demás secretos requeridos —
antes de desplegar esta fase, confirmar que todos están configurados
(`configuraciones.wa_*` o `.env`).
