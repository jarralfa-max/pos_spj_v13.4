# SDLC-INV-008 — Destinatarios de alertas de stock por texto de rol legacy y teléfonos globales, fuera del RBAC

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `inputs/correcciones.md` C-10 (oleada 5); auditoría `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` §3 «P1 — Alertas de stock están implementadas, con alcance operativo que validar»
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ARQ-PERM-003, SDLC-ARQ-PERM-005

## Problema
Las alertas de stock mínimo eligen a quién avisar comparando el texto de `usuarios.rol` con una lista de roles en ajustes, no con la asignación de roles RBAC ni con su alcance. Un usuario sin sucursal recibe las alertas de todas. Los teléfonos de WhatsApp son una lista global: cada alerta de cualquier sucursal va a los mismos números.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado el 2026-10-31 sobre `4639fed2`.

- `backend/application/products/queries/product_settings_query.py:65-80` — `alert_user_ids`: `SELECT id FROM usuarios WHERE lower(trim(rol)) IN (...)` y `AND (sucursal_id=? OR sucursal_id IS NULL OR sucursal_id='')`; `except Exception` → nadie a quien avisar.
- `backend/application/products/queries/product_settings_query.py:18-19,57-58` — `products.alerts.whatsapp_phones`: lista única global.
- `backend/application/inventory/notifications/stock_minimum_monitor.py:51,67-76` — usa esos usuarios (IN_APP) y esos teléfonos (WHATSAPP) para cada regla de cada sucursal/almacén.
- **No verificado:** si el envío por WhatsApp desde el `.exe` queda en cola persistente y reintentable sin conexión (`FanOutProductNotificationGateway`); se medirá en Design.

## Impacto
Avisos a personas sin relación con la sucursal o el almacén (fuga de información operativa) y avisos que no llegan a los responsables reales.

## Objetivo
- Destinatarios desde la fuente RBAC con alcance por sucursal y responsables por almacén.
- WhatsApp por sucursal/almacén, en cola persistente y reintentable, también offline en el `.exe`.
- Sin crear otro centro de notificaciones (se usa el existente).

## Alcance
- **Incluye:** resolución de destinatarios, configuración de teléfonos por ámbito, cola de WhatsApp de alertas.
- **No incluye:** el microservicio WhatsApp roto (SDLC-WA-005, SDLC-WA-006); contador de notificaciones del shell (SDLC-UI-015).

## Restricciones
CLAUDE.md regla 13; una sola fuente de permisos (`InventoryScopePolicy`/resolvedor canónico); sin pantalla duplicada en Configuración; presupuesto $0; Windows. Nivel T1 según el responsable; nota: toca `backend/application/inventory/notifications` (área T0 en el README) solo en la lectura de destinatarios.

## Trabajo previo relacionado
Memoria PROD-22 (outbox de alertas WA); memoria «Alcance por sucursal: dos reglas incompatibles»; SDLC-WA-005/006.

## Preguntas abiertas
- ¿Qué permiso o rol RBAC define «recibe alertas de stock» (permiso nuevo `INVENTARIO.alertas.recibir` o responsables por almacén)? responsables por almacen · bloquea `/sdlc-design SDLC-INV-008`
- ¿Los teléfonos de WhatsApp se configuran por sucursal, por almacén o se toman del usuario destinatario? · bloquea `/sdlc-design SDLC-INV-008` del usuario destinatario 
