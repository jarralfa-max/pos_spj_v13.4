# SDLC-WA-037 — Notificaciones del ERP al cliente por /api/notify v1 sin outbox; la v2 no tiene llamadores y nadie decide el canal

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §50 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-018

## Problema
El ERP solo llama `/api/notify/pedido-listo` y `/api/notify/send` (v1), que envían en línea sin outbox ni idempotencia; la v2 con outbox no tiene llamadores. `resolve_route` de Notificaciones tiene cero llamadores: cada módulo decide el canal por su cuenta. Faltan avisos de §50 (en preparación, repartidor asignado, cotización por vencer, puntos ganados, recompensa, tarjeta, sorteo). El aviso de pago recibido pasa `external_reference` (que puede ser `venta_id:teléfono`) como teléfono (**no verificado** contra un pago real).

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `backend/infrastructure/integrations/whatsapp_client.py:128-184`; `whatsapp_service/router/notify_router.py:68-100`; `router/notify_dispatch_router.py:6-7,67-108`
- `backend/domain/notifications/policies/notification_routing_policy.py:15-19` — sin llamadores
- `whatsapp_service/webhook/mercadopago.py:99`; `flows/pago_flow.py:87`
- Pruebas: `whatsapp_service/tests/test_notify_dispatch_router.py` (v2); `tests/test_wa_client.py` (no se recolecta)

## Impacto
Avisos perdidos o duplicados; cada módulo con su propia regla de canal.

## Objetivo
- Los módulos publican eventos; Notificaciones decide canal, plantilla y destinatario; el canal entrega por outbox.
- Se retira `/api/notify` v1.
- Lista de avisos de §50 cubierta o descartada explícitamente.

## Alcance
- **Incluye:** Ruta de notificaciones ERP→canal.
- **No incluye:** Reintento de avisos de Pedidos (SDLC-ORD-006, que este ítem resuelve de forma general); despacho de outbox de otros contextos (SDLC-ORD-002).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-ORD-006; SDLC-ORD-002; WA-18 (memoria).

## Preguntas abiertas
- Ninguna por ahora.
