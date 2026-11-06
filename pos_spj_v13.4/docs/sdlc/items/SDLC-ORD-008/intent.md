# SDLC-ORD-008 — Clic en un aviso de la campana no abre el pedido: solo lo marca como leído

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/WHATSAPP_DELIVERY_CLOSEOUT_STATUS.md` → "Pendiente de cierre 100%" y "Recomendación de último PR técnico" §1-2 (deep-link de la notificación al pedido exacto y su prueba de integración), re-verificado en código (`/sdlc-plan` Modo B, 2026-10-31)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** —

## Problema
Los avisos internos de Pedidos llegan a la campana de la barra superior. Al abrir uno, la app solo lo marca como leído y no lleva al pedido. El aviso sí guarda el pedido (`datos` incluye `order_id`), pero `NotificationItem` no transporta esa referencia y nadie convierte el clic en navegación. El cierre de WhatsApp→Delivery pedía conectarlo en `main_window`. Ese archivo ya no existe; el shell vigente es `ApplicationWindow`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado directamente el 2026-10-31 sobre `ed026f7b`.

- `frontend/desktop/shell/application_shell/notification_drawer.py:32-37`: `NotificationItem` solo tiene `notification_id`, `title`, `message`, `created_at` y `read`, sin destino.
- `notification_drawer.py:141-144`: `_on_item_activated` → `mark_read` + `notification_activated.emit(notification_id)`.
- `frontend/desktop/shell/application_shell/notification_inbox_feed.py:37`: la única conexión de `notification_activated` es `self.mark_read`. En `:55-58` arma `NotificationItem` sin leer `datos`.
- `migrations/m000_base_schema.py:2747`: `notification_inbox.datos TEXT DEFAULT '{}'`.
- `backend/application/orders_delivery/use_cases/dispatch_use_cases.py:218-223`: la alerta de entrega fallida guarda `datos={"delivery_job_id": ..., "order_id": ...}`.
- `main_window.py`/`menu_lateral.py` ya no existen (shell canónico en `frontend/desktop/shell/desktop_shell_window_composition.py`).
- Los avisos que manda el microservicio (`notify_*` del cierre WA) no llegan hoy a la bandeja del POS (SDLC-WA-005). Para esos, el deep-link depende de ese ítem.

## Impacto
El gerente ve "Entrega fallida — pedido X" y tiene que ir a buscarlo a mano. Pasa lo mismo con avisos de CRM y productos que también traen referencia.

## Objetivo
- Abrir un aviso con referencia conocida (`order_id`, `delivery_job_id`) navega a la ruta y al registro exactos de Pedidos, respetando permisos y sucursal.
- Un aviso sin referencia o de un módulo sin destino sigue marcándose como leído, sin error.
- Hay una prueba de integración de UI del ruteo del clic (pendiente §2 del cierre).

## Alcance
- **Incluye:** Contrato de destino del aviso (leído de `datos`), ruteo en el shell hacia Pedidos y prueba.
- **No incluye:** Llevar los avisos del microservicio a la bandeja (SDLC-WA-005) ni el deep-link de otros módulos, salvo que el contrato quede genérico sin costo extra.

## Restricciones
Sin SQL en UI (CLAUDE.md regla 13); el feed solo presenta (`notification_inbox_feed.py:8-9`); `docs/skills/SPJ_REFACTOR_SKILL.md` (UUIDv7, rutas dentro de `pos_spj_v13.4/`); presupuesto $0; Windows. Nivel T2: plan corto y pruebas afectadas (`tests/ui` con fixture de `QApplication` a nivel de módulo).

## Trabajo previo relacionado
CRM-43 (campana conectada a `notification_inbox`); SHELL-11; SDLC-WA-005.

## Preguntas abiertas
- Ninguna por ahora.
