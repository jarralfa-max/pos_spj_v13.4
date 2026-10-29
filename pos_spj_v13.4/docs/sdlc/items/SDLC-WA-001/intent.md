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
