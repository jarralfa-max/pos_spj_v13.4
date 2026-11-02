# SDLC-WA-010 — Webhook de Meta sin ventana de tiempo, sin anti-replay persistido ni registro de intentos inválidos

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §18 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-002

## Problema
La firma `X-Hub-Signature-256` se valida en tiempo constante, pero no hay política de timestamp para Meta, el único anti-replay es el dedupe por `message_id`, no se guarda hash del payload ni id del evento del proveedor, y un intento con firma inválida solo deja un `logger.warning` con la IP. Mercado Pago no tiene almacén de `x-request-id`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/webhook/whatsapp.py:69-74` — firma; `:91-95` comentario: sin timestamp
- `whatsapp_service/middleware/hmac_validator.py:57-63` — ventana de 300 s solo para Mercado Pago
- `whatsapp_service/state/conversation.py:118-135` — solo `message_id` en `message_log`
- `whatsapp_service/webhook/whatsapp.py:73` — intento inválido solo en log
- Pruebas: `tests/test_wa_phase9_regression.py::test_webhook_invalid_signature_returns_403`; `whatsapp_service/tests/test_mercadopago_webhook_signature.py`

## Impacto
Seguridad: un payload firmado capturado se puede reenviar; los ataques no dejan rastro consultable.

## Objetivo
- Cada entrega del webhook se registra con hash del payload e id del proveedor y se rechaza si se repite.
- Los intentos inválidos quedan en una tabla consultable (sin secretos) con contador para alertas.

## Alcance
- **Incluye:** Política de replay y registro de entregas del webhook.
- **No incluye:** Modo fail-closed por `APP_ENV` (SDLC-WA-002).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-WA-002 (spec aprobado).

## Preguntas abiertas
- Ninguna por ahora.
