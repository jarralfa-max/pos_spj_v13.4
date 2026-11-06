# SDLC-ORD-006 — Avisos al cliente de Pedidos sin reintento: si WhatsApp falla, el mensaje se pierde

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** auditoría `docs/audits/DELIVERY_REFACTOR_AUDIT.md` (Riesgos detectados §7: "Reintentos inexistentes en notificaciones críticas"), re-verificado en el estrato canónico (`/sdlc-plan` Modo B, 2026-10-31)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** —

## Problema
Los avisos al cliente ("va en camino", "entregado", "no pudimos entregar", "requiere aprobación", "listo para recoger") se mandan con una sola llamada HTTP síncrona al microservicio. Si falla, la excepción se traga, se registra un warning y el mensaje no se vuelve a intentar. La alerta interna de entrega fallida tiene el mismo patrón (`except Exception` y solo log). No hay cola ni outbox para estos avisos, aunque el repositorio ya tiene ese patrón en otros contextos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado directamente el 2026-10-31 sobre `ed026f7b`.

- `backend/application/orders_delivery/use_cases/dispatch_use_cases.py:41-50`: `_notify_customer` llama a `whatsapp.send_message` dentro de `try/except Exception` → `logger.warning` y `return False`.
- `dispatch_use_cases.py:216-225`: la alerta interna también va en `try/except` y solo se registra.
- `backend/infrastructure/integrations/orders_delivery_whatsapp_client.py:68-78`: `send_message` traga cualquier excepción y devuelve `False`.
- `backend/infrastructure/integrations/whatsapp_client.py:183-184` (`enviar_mensaje` → `_post("/api/notify/send")`) y `:165` (`urllib.request.urlopen`): un solo intento, sin cola.
- Patrones existentes: `product_whatsapp_outbox` (`backend/infrastructure/db/schema/products_schema.py:293`, PROD-22) y `whatsapp_outbox` (`backend/infrastructure/db/schema/whatsapp_schema.py:202`). No se comprobó si alguno tiene despachador vivo: **no verificado**.
- Lo legacy que cita la auditoría (`core/services/delivery_whatsapp_service.py`) ya no existe (borrado en `a35b8bab`, 2026-09-10). El riesgo sigue vivo en el código canónico.

## Impacto
Si el microservicio está caído o lento, los clientes no se enteran de que su pedido va en camino o falló, y nadie en la sucursal lo ve. No se encontró dónde se guarda `notification_sent=False` para poder consultarlo: **no verificado**.

## Objetivo
- Cada aviso al cliente de Pedidos queda persistido antes de enviarse y se reintenta con límite y backoff, de forma idempotente por `operation_id`.
- Los avisos agotados quedan visibles para la sucursal.
- Se reutiliza un outbox o cola de WhatsApp existente; no se crea un tercero.

## Alcance
- **Incluye:** Avisos al cliente y alerta interna de Pedidos, persistencia y reintento, y pruebas de falla del cliente HTTP.
- **No incluye:** Drenado general de los outbox de Pedidos/CRM (SDLC-ORD-002), trabajadores del microservicio (SDLC-WA-006) ni la política configurable (SDLC-ORD-011).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
ORD-23 y ORD-26 (`docs/refactor/ORD-23_*.md`, `ORD-26_*.md`); SDLC-ORD-002; SDLC-WA-006; PROD-22 (outbox de alertas WA de productos).

## Preguntas abiertas
- ¿Se unifica sobre `whatsapp_outbox` o sobre el outbox de Pedidos? Decidirlo en Design junto con SDLC-ORD-002. sobre whatsapp_outbox

## Ampliación 2026-11-01 (`/sdlc-plan arquitectura docs/sdlc/inputs/whatsapp.md`)
Origen: `docs/sdlc/inputs/whatsapp.md` §50, §21; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`.
- Además del reintento, el cliente de Pedidos se construye sin conexión y solo lee la credencial de variables de entorno: ver SDLC-WA-038.
- La ruta general ERP→canal por outbox (retiro de `/api/notify` v1) es SDLC-WA-037; la pregunta de este ítem sobre qué outbox usar se decide allí.
