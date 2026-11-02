# SDLC-WA-001 — Webhook de MercadoPago puede confirmar el pedido equivocado y pierde aprobaciones

- **Prioridad:** P0
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-002

## Problema
El webhook sólo procesa `payment.created` (las aprobaciones llegan como `payment.updated`), localiza la venta por los últimos 10 dígitos del teléfono contra la venta `pendiente_wa` más reciente sin comparar el monto contra el anticipo esperado, intenta `int(pref)` contra IDs UUID, se traga errores con `except Exception: pass` y avisa 'pago recibido' al cliente antes de casar el pago.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `whatsapp_service/webhook/mercadopago.py:65` — sólo `payment.created`
- `whatsapp_service/webhook/mercadopago.py:99-130` — búsqueda por teléfono, `int(pref)` (112-115), `except Exception: pass` (129)
- `whatsapp_service/webhook/mercadopago.py:99,145` — mensaje al cliente antes del match

## Impacto
Dinero: un pago puede confirmar otro pedido o perderse; el cliente cree que pagó algo que no quedó registrado.

## Objetivo
- El pago se casa por referencia externa (UUID) y monto; si no casa queda en una bandeja de pagos sin asignar.
- Se procesan los estados de aprobación reales del proveedor de pagos.
- El cliente sólo recibe confirmación después de un match exitoso.
- Errores de búsqueda quedan registrados y visibles, no tragados.

## Alcance
- **Incluye:** `webhook/mercadopago.py` y su prueba.
- **No incluye:** Registro contable del anticipo (SDLC-WA-004); firma del webhook (SDLC-WA-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Microservicio WhatsApp: preservar los 3 shims de CLAUDE.md regla 9; el cutover del webhook a WA-1..20 sigue diferido por decisión del usuario.

## Trabajo previo relacionado
`docs/refactor/WA-22_validacion_final.md` (gaps abiertos); `docs/audits/WHATSAPP_AUDIT.md`. Respetar los 3 shims de WhatsApp de CLAUDE.md regla 9.

## Preguntas abiertas
- ¿Se usa MercadoPago en producción hoy, o el flujo está apagado?

## Ampliación 2026-10-29 (`/sdlc-plan arquitectura docs/sdlc/inputs/mercado-pago.md`)
Origen: `docs/sdlc/inputs/mercado-pago.md` Fase 7; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md` (Fase 7 «Persistir antes de 200, dedup…», `defectuoso`, CRITICAL). Evidencia nueva, mismo archivo y mismo alcance:

- `whatsapp_service/webhook/mercadopago.py:145` — la idempotencia usa `confirm_payment:{venta_id}:{monto}`: dos pagos legítimos del mismo monto a la misma venta se funden en uno; debe ser el id de pago/notificación (*verificado directamente*).
- `whatsapp_service/webhook/mercadopago.py:61-62,78-79,86-87,166-169` — responde HTTP 200 con JSON inválido, sin token, si la consulta a MP falla y en el `except` general, sin haber persistido nada: Mercado Pago no reintenta y el evento se pierde.
- `whatsapp_service/webhook/mercadopago.py:35` — sin límite de tamaño del cuerpo.
- `whatsapp_service/webhook/mercadopago.py:89-94` — no compara monto, moneda ni cuenta cobradora (`collector_id`) contra lo esperado.
- `whatsapp_service/webhook/mercadopago.py:100` — `notificar_pago_recibido` recibe `external_ref` (`venta_id:phone`) como teléfono.
- `whatsapp_service/webhook/mercadopago.py:122-126` — un `venta_id` en `external_reference` tiene prioridad sin verificar estado ni teléfono; `:151` emite `PAYMENT_RECEIVED` aun con `venta_id` 0.
- `whatsapp_service/erp/gateways/payment_gateway.py:39` — en modo API llama `POST /api/v1/anticipos/{id}/confirmar`, ruta inexistente; el error se traga y el pago se pierde.
- Prueba: sólo firma y fail-closed (`whatsapp_service/tests/test_mercadopago_webhook_signature.py`, `test_webhook_production_fail_closed.py`); la lógica de negocio no tiene ninguna. `test_mercadopago_webhook_signature.py:106-116` fija como esperado ignorar `payment.updated`.

El receptor definitivo (inbox durable, firma, consulta autorizada) es SDLC-PAY-010; este ítem sigue siendo la corrección del receptor que existe hoy.

## Ampliación 2026-11-01 (`/sdlc-plan arquitectura docs/sdlc/inputs/whatsapp.md`)
Origen: `docs/sdlc/inputs/whatsapp.md` §38, §39, §19; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`.
- En el camino vivo nunca se crea la fila de `anticipos` (el orquestador no se inyecta: `whatsapp_service/router/message_router.py:189-195`), así que `UPDATE ventas SET estado='confirmada', anticipo_pagado=?` corre con **cualquier monto** aprobado (`whatsapp_service/erp/gateways/payment_gateway.py:46-55`, *verificado directamente*).
- La clave de idempotencia es `confirm_payment:{venta}:{monto}` sin `payment_id` (`whatsapp_service/webhook/mercadopago.py:144-145`, *verificado directamente*): dos pagos reales del mismo monto se fusionan; `PAYMENT_RECEIVED` y el aviso al cliente se re-emiten en cada webhook (`:99-165`).
- Relacionados nuevos: SDLC-WA-012 (identidad por sufijo de teléfono), SDLC-WA-015 (re-emisión de eventos de negocio).
