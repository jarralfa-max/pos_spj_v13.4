# SDLC-WA-018 — Dos caminos de envío a Meta: flujos y router llaman al sender legacy sin pasar por el gateway ni persistir antes de enviar

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §22, §21 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-016

## Problema
El puerto `WhatsAppProviderGateway` y `MetaCloudApiWhatsAppGateway` existen, pero 29 archivos (todos los flujos, router, notificaciones) llaman directo a `messaging.sender`. Las confirmaciones de pedido o pago salen sin persistirse antes: si falla el envío solo queda el log. `get_message_status` devuelve siempre None. El flujo de pago llama a Mercado Pago con httpx directo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/messaging/sender.py:63-107,165-234` — única transporte; sin persistencia
- `whatsapp_service/flows/pedido_flow.py:18`; `router/message_router.py:40`; `messaging/interactive.py:9`; `router/notify_router.py:59,95`
- `whatsapp_service/infrastructure/providers/meta_cloud_api/gateway.py:32-220`, `:134-144` (estado siempre None)
- `whatsapp_service/flows/pago_flow.py:79-117` — httpx directo
- Prueba: `whatsapp_service/tests/test_meta_cloud_api_gateway.py` (gateway aislado)

## Impacto
Mensajes críticos perdidos sin rastro; dos lugares donde cambiar formato, límites o consentimiento.

## Objetivo
- Un solo sender: todo envío pasa por el gateway desde el outbox.
- Toda salida crítica se persiste antes de enviarse.
- Ningún flujo importa httpx/requests.

## Alcance
- **Incluye:** Consolidación del envío.
- **No incluye:** Reintentos y dead letter (SDLC-WA-039); notificaciones del ERP (SDLC-WA-037).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-5, WA-17 (memoria).

## Preguntas abiertas
- Ninguna por ahora.
