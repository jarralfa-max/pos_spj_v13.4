# SDLC-WA-002 — Plan de implementación

- **Spec:** `items/SDLC-WA-002/spec.md` (aprobado el 2026-10-28, Alfred; D1=B, D2=B, D3=A)
- **Rama:** `sdlc/sdlc-wa-002` desde `claude/erp-financial-bounded-context-uqxz6b` @ `850fcb11`
- **Estado:** borrador

## Línea base

Medida el 2026-10-28 sobre `850fcb11`, antes de cualquier cambio. Windows 11, Python 3.13. Salidas completas en el scratchpad de la sesión (`baseline_wa.txt`, `baseline_pos_wa.txt`, `baseline_arch.txt`).

| # | Comando | Resultado real |
|---|---|---|
| B1 | `python -m pytest whatsapp_service/tests -q` (desde la raíz del repo) | ❌ **no colecta**: `1 error during collection` (`test_adjustment_approval_phase7.py` importa `core.delivery`, que ya no existe). |
| B1b | igual + `--continue-on-collection-errors` | ❌ **15 failed, 699 passed, 1 error** (25.8 s). Idéntico con `PYTHONPATH=pos_spj_v13.4`. |
| B2 | `python -m pytest tests/test_wa_*.py -q --continue-on-collection-errors` (desde `pos_spj_v13.4/`) | ❌ **22 failed, 67 passed, 35 errors** (12.5 s). |
| B3 | `python -m pytest tests/architecture -q` (desde `pos_spj_v13.4/`) | ❌ **22 failed, 879 passed, 1 skipped, 2 xfailed** (1459 s). Son las mismas 22 de `docs/sdlc/baseline/2026-10-28.md`; entre ellas `test_whatsapp_runtime_imports.py::test_channel_uses_qualified_imports` (WA-005), que este ítem no toca. |

Fallas previas que caen **dentro** del alcance de este ítem:
- `whatsapp_service/tests/test_mercadopago_webhook_signature.py::test_webhook_accepts_valid_signature_and_ignores_non_payment_action`: el parámetro de consulta se envía como `whatsapp_service.data.id`, no `data.id` (spec §0). Lo corrige el paso 2.

Fallas previas **fuera** de alcance (no se tocan; deben seguir iguales al final):
- B1b, las otras 14: `test_bridge_notification_routing`, `test_conversation_quote_context`, `test_cotizacion_flow_phase6`, `test_intent_resolver` (1), `test_intent_resolver_ai_paths` (5), `test_message_router_branch_switch`, `test_message_router_intent_resolver_integration` (2), `test_wa_event_log_insert` (2), más el error de colección de `test_adjustment_approval_phase7.py` (ya registrado como WA-005 en el baseline).
- B2: las 22 fallas y 35 errores (`test_wa_orchestrator`, `test_wa_parser`, `test_wa_refactor`, `test_wa_bridge`, `test_wa_client`, `test_wa_repositories`, `test_wa_admin_bounded_context_visibility`, y en `test_wa_phase9_regression` dos fallas: `test_webhook_invalid_signature_returns_403` y `test_sender_fails_without_credentials`).

Pruebas que **hoy pasan sólo por el fail-open** y que este cambio rompe a propósito (se actualizan, no se borran):
- `whatsapp_service/tests/test_webhook_production_fail_closed.py`: `test_whatsapp_webhook_allows_with_warning_outside_production`, `test_mercadopago_webhook_allows_with_warning_outside_production`.
- `whatsapp_service/tests/test_mercadopago_webhook_signature.py::test_webhook_falls_back_to_unsigned_when_secret_not_configured`.
- `pos_spj_v13.4/tests/test_wa_phase9_regression.py`: `test_webhook_status_update_is_ignored`, `test_webhook_group_message_is_ignored`, `test_webhook_rate_limit_blocks_processing`. Llaman a `receive_message` sin secreto para probar la lógica posterior a la firma. **No los menciona el spec**: los encontré al medir la línea base. Se les agrega el opt-in, igual que a los de arriba.

## Pasos

Comando de verificación común (desde la raíz del repo): `python -m pytest <archivos> -q -p no:cacheprovider`. Cada paso termina en un commit `test|fix|feat|docs(whatsapp): … [SDLC-WA-002]`.

| # | Archivo(s) | Cambio | Verificación del paso |
|---|---|---|---|
| 1 | `whatsapp_service/tests/test_webhook_signature_contract.py` (nuevo) | **Regresión que fija lo que no se mueve.** Con secreto configurado (getters doblados con `monkeypatch`), una firma inválida o ausente da **403** en `POST /webhook` y en `POST /webhook/mercadopago`, parametrizado con `APP_ENV` ∈ {sin valor, `development`, `test`, `production`} y con y sin `WA_ALLOW_UNSIGNED_WEBHOOKS=1`. El router doble y la API de pagos no reciben llamadas. Un fixture `autouse` limpia `APP_ENV`, `ENVIRONMENT` y `WA_ALLOW_UNSIGNED_WEBHOOKS`. | Pasa **sobre el código actual** (antes del paso 3). Cubre el criterio 6. |
| 2 | `whatsapp_service/tests/test_mercadopago_webhook_signature.py` | Cambia las tres ocurrencias de `whatsapp_service.data.id` por `data.id` (líneas 89, 99, 111). | `test_webhook_accepts_valid_signature_and_ignores_non_payment_action` pasa; el resto del archivo sigue igual. Criterio 8. |
| 3 | `whatsapp_service/config/settings.py`; `whatsapp_service/tests/test_settings_webhook_security.py` (nuevo) | Agrega:<br>• `allow_unsigned_webhooks() -> bool` (regla 3: opt-in ∈ {`1`,`true`,`yes`} ∧ ¬`is_production()` ∧ ¬`_APP_PATHS.is_installed`; llama a `is_production` por el nombre del módulo).<br>• `unsigned_webhook_rejection(secret_name) -> str`: el único texto del `error` de 503. Nombra el secreto faltante y dice por qué no hay opt-in: no se pidió, se ignoró por producción o se ignoró por estación instalada. No incluye valores.<br>• `describe_webhook_security() -> dict` con `env`, `installed`, `unsigned_allowed`, `unrecognized_env_value`.<br>• `get_mp_signature_max_age_seconds() -> int` (D2): lee `MP_SIGNATURE_MAX_AGE_SECONDS` en cada llamada; default 300; un valor no entero o ≤ 0 vuelve a 300 con `warning`.<br>`get_app_env()` conserva firma y resultado; sólo se extrae la lectura cruda a `_raw_app_env()` para poder reportar el valor no reconocido. | Pruebas unitarias nuevas: valores del opt-in, opt-in ignorado en producción y en layout instalado (`AppPaths(layout=LAYOUT_INSTALLED)` vía `monkeypatch` de `_APP_PATHS`), los tres textos de rechazo, valor no reconocido (`prd`), ningún valor de secreto en el dict y casos de la ventana. Más las suites existentes que doblan `is_production` (`test_main_production_gate`, `test_lifecycle`, `test_health_checks`, `test_service_auth`), sin cambios. |
| 4 | `whatsapp_service/middleware/hmac_validator.py`; `whatsapp_service/tests/test_mercadopago_webhook_signature.py` | `verify_mp_signature` conserva su firma pública. Normaliza `ts` (< 10¹² → segundos × 1000; ≥ 10¹² → ms), rechaza `ts` no numérico y registra cada rechazo con motivo propio en el logger `wa.hmac`: `firma no coincide`, `ts no numérico`, `ts fuera de ventana (edad=…s, máx=…s)`. Corrige la docstring («`ts` is milliseconds»). | Pruebas nuevas: aceptación con `ts` actual en segundos (10 dígitos) y en ms (13 dígitos); rechazo de ambas unidades fuera de ventana; `ts` no numérico; `caplog` distingue antigüedad de firma inválida. Las pruebas existentes de ventana siguen pasando. Criterio 7. |
| 5 | `whatsapp_service/webhook/whatsapp.py`; `whatsapp_service/tests/test_webhook_production_fail_closed.py`; `pos_spj_v13.4/tests/test_wa_phase9_regression.py` | La rama `elif is_production(): 503 / else: warning` pasa a `elif allow_unsigned_webhooks(): warning / else: error(unsigned_webhook_rejection("WA_APP_SECRET")) + 503`. El resto del handler queda igual.<br>Pruebas: `…allows_with_warning_outside_production` exige el opt-in. Se agregan los criterios 1-5 con un payload de texto real, routers y conversation store dobles que registran llamadas (restaurados al terminar) y `caplog`. En `test_wa_phase9_regression.py`, los tres tests que dependían del fail-open reciben `monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")`. | Archivos del paso + paso 1 en verde. `test_wa_phase9_regression.py` queda con las mismas 2 fallas previas y nada más. Criterios 1-5 (Meta) y 11. |
| 6 | `whatsapp_service/webhook/mercadopago.py`; `whatsapp_service/tests/test_webhook_production_fail_closed.py`; `whatsapp_service/tests/test_mercadopago_webhook_signature.py` | Mismo cambio de rama con `"MP_WEBHOOK_SECRET"`. Pasa `max_age_seconds=get_mp_signature_max_age_seconds()` a `verify_mp_signature`. El log de 403 dice «notificación rechazada» (el motivo ya lo registró el paso 4).<br>Pruebas: criterios 1-5 para MercadoPago. Con `action=payment.created` y `MP_ACCESS_TOKEN` doblado, se comprueba que `httpx.AsyncClient` **no** se construye. `…falls_back_to_unsigned…` exige el opt-in y se le agrega su par sin opt-in que espera 503. Prueba de que la ventana configurada llega al validador. | Archivos del paso + pasos 1, 2 y 4 en verde. Criterios 1-5 (MP), 8 y 11. |
| 7 | `whatsapp_service/main.py`; `whatsapp_service/tests/test_main_production_gate.py` | Nueva función standalone `_log_webhook_security_status()`, mismo patrón que `_assert_production_secrets_configured`. Emite **una** línea con el entorno efectivo, `instalado=sí/no` y `webhooks_sin_firma=permitido/bloqueado`: `warning` si está permitido, `info` si no. Más un `warning` aparte si `APP_ENV`/`ENVIRONMENT` no se reconoce. `lifespan` la llama justo después del gate. | Pruebas con `caplog` sobre la función aislada: una sola línea de estado, el nivel correcto en cada caso y el `warning` extra con `prd`. Las pruebas existentes del gate siguen en verde. Criterio 9. |
| 8 | `whatsapp_service/bootstrap/health_checks.py`; `whatsapp_service/tests/test_health_checks.py` | Nueva `check_webhook_signature(root)`: HEALTHY con secreto de Meta; DEGRADED sin secreto y con opt-in válido; UNHEALTHY sin ninguno, con detalle accionable («configura WA_APP_SECRET en el módulo WhatsApp»). Se registra en `run_all_checks` junto a `check_secrets`. | Pruebas de los tres estados, prueba de que el detalle nunca contiene el valor del secreto (extiende `test_detail_never_contains_a_secret_value`) y `test_shape` incluye `webhook_signature`. Criterio 10. |
| 9 | `whatsapp_service/service_host.py` | Sólo docstring: agrega `APP_ENV=production` al ejemplo de `whatsapp.env` y explica que `WA_APP_SECRET` es obligatorio para recibir webhooks y que `WA_ALLOW_UNSIGNED_WEBHOOKS` se ignora en una estación instalada. | `python -c "import ast; ast.parse(open('whatsapp_service/service_host.py', encoding='utf-8').read())"`. |
| 10 | `pos_spj_v13.4/migrations/MIGRATION_LOG.md`; `BACKLOG.md`; este plan | Entrada en el log: el cambio de comportamiento, sin migración de esquema, y la acción operativa de D3. Etapa → `en-test`. **Corrida final**: B1b, B2 y B3. | B1b: las mismas 14 fallas previas fuera de alcance + 1 error de colección, **0 fallas nuevas**, y `test_webhook_accepts_valid_signature…` ahora pasa. B2: mismas fallas y errores, sin nuevas. B3: ≤ 22 fallas y las mismas. Criterio 12. |

## Archivos que NO se tocan

- `pos_spj_v13.4/services/whatsapp_service.py` e `pos_spj_v13.4/integrations/whatsapp_service.py`: shims v12 intencionales (CLAUDE.md §9).
- `whatsapp_service/webhook/whatsapp.py` **sí** se toca, pero sólo la rama de firma de `receive_message`. Es el tercer «shim» que CLAUDE.md §9 pide preservar: se conservan la ruta, `router`, `init_webhook` y los globals que inyecta `main.py`.
- `whatsapp_service/erp/bridge.py` (`is_production()` en 214/221), `main.py::_assert_production_secrets_configured`, `bootstrap/lifecycle.py` y la severidad de `check_secrets`: D1=B deja los demás usos de `is_production()` como están hasta SDLC-WA-003.
- `get_app_env()`: no cambia su normalización; un valor no reconocido sigue siendo `development` (spec, regla 5).
- `whatsapp_service/bootstrap/application_factory.py`: tiene su propio `lifespan`. El spec sólo pide el log en `main.py` y aquí no se extiende.
- Matching del pago de MercadoPago (`mercadopago.py:65` en adelante): SDLC-WA-001. Contrato REST del ERP: SDLC-WA-003.
- Manifiesto de MercadoPago con `id:;` cuando falta `data.id`: **no verificado** contra el proveedor. El spec lo deja fuera y no lo llevo al backlog porque Build no lo confirma.

## Migraciones

No hay. Sin cambios de esquema ni de datos. **Reversa:** revertir los commits del ítem. Mitigación en una máquina de desarrollo: `WA_ALLOW_UNSIGNED_WEBHOOKS=1`. En una estación instalada: configurar `WA_APP_SECRET` (D3=A). La nota de release con esa acción se redacta en Deploy.

## Observaciones de la línea base (no se arreglan aquí)

- `get_app_secret()` y `get_mp_webhook_secret()` consultan primero el `SecretStore`, que lee la BD del ERP resuelta por `AppPaths`; en una copia de código fuente es `pos_spj_v13.4/data/spj_pos_database.db`. Las pruebas existentes que doblan `MP_WEBHOOK_SECRET` en vez del getter dependen de que esa base no tenga `wa_mp_webhook_secret`. **No verifiqué** si el store abre esa base durante las pruebas. Las pruebas nuevas doblan los getters para no depender de ello. Si en Test se confirma, va al backlog como `intent-borrador`.

## Criterio de terminado

| Criterio del spec | Prueba |
|---|---|
| 1. Sin secreto, sin opt-in, sin `APP_ENV` → 503, router/API no llamados, `error` nombra el secreto | paso 5 (Meta) y paso 6 (MP), `test_webhook_production_fail_closed.py` |
| 2. Igual con `development`, `test`, `prd` | mismos, parametrizados |
| 3. Opt-in + no producción + código fuente → 200 y el router recibe | pasos 5/6 |
| 4. Opt-in + `production` → 503, error «ignorado por producción» | pasos 5/6 + paso 3 (texto) |
| 5. Opt-in + instalado → 503, error «ignorado por estación instalada» | pasos 5/6 + paso 3 (texto) |
| 6. Secreto + firma inválida → 403 siempre | paso 1, `test_webhook_signature_contract.py` |
| 7. `verify_mp_signature`: segundos/ms, ventana, no numérico, motivo distinto | paso 4 |
| 8. E2E con firma válida y `data.id` real | paso 2 |
| 9. Una línea de estado al arrancar + warning por `APP_ENV` no reconocido | paso 7 |
| 10. `check_webhook_signature` HEALTHY/DEGRADED/UNHEALTHY sin secretos en el detalle | paso 8 |
| 11. Pruebas del comportamiento anterior actualizadas, no borradas | pasos 5/6 |
| 12. Sin fallas nuevas en `whatsapp_service/tests` ni en `tests/architecture` | paso 10 |
| D2. `MP_SIGNATURE_MAX_AGE_SECONDS` configurable, default 300 | pasos 3 y 6 |
