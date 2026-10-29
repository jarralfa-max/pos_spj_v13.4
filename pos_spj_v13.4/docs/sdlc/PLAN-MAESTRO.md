# Plan maestro SDLC — SPJ ERP

Une todo el trabajo pedido en un solo orden. Cada línea de trabajo se ejecuta como ítems del SDLC (intent → spec → plan → build → test → deploy); ninguna se ejecuta como un prompt largo.

## Fuentes (todas en `docs/sdlc/inputs/`)

| Fuente | Qué es | Cómo entra al backlog |
|---|---|---|
| Triage del 2026-10-28 | Defectos del código actual | Ya está en `BACKLOG.md` |
| `requisitos-arquitectura.md` | Arquitectura offline-first: permisos, terminales, sesiones, caja y turno compartidos, sincronización, PostgreSQL/FastAPI, instalador | `/sdlc-plan arquitectura` |
| `correcciones.md` | Auditoría del 2026-10-26: recepción, transferencias, despiece, unidades, precios | Modo B, punto por punto |
| `ui-ux.md` | Design System JUANIS, shell, navegación, densidades, guardrails | `/sdlc-plan arquitectura docs/sdlc/inputs/ui-ux.md` |
| `mercado-pago.md` | Integración Point Smart, Checkout, QR, webhooks, conciliación | `/sdlc-plan arquitectura docs/sdlc/inputs/mercado-pago.md` |
| `activos.md` | EAM de Activos (prompt ASSET-0 a ASSET-24) | `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` |
| `whatsapp.md` | Canal WhatsApp enterprise (prompt WA-0 a WA-22) | `/sdlc-plan arquitectura docs/sdlc/inputs/whatsapp.md` |
| Repartos (sin prompt propio) | Pendientes de `docs/refactor/ORD-30_validacion_final.md`, `docs/WHATSAPP_DELIVERY_CLOSEOUT_STATUS.md` y `docs/audits/DELIVERY_REFACTOR_AUDIT.md` | Modo B, un intent por pendiente |

## Lo que ya existe (revisado en `16eb1d8e`, para no rehacerlo)

- **UI:** ya existen la mayoría de los componentes que pide `ui-ux.md`: `frontend/desktop/components/` (`standard_window.py`, `dialogs.py` con StandardDialog, `tables.py`, `kpi_card.py`, `page_viewport.py`, `icons.py`, `branding.py`, `virtual_keyboard.py`, `side_nav.py`), `shell/sidebar/global_sidebar.py`, `shell/application_shell/notification_drawer.py`, perfiles de densidad en `backend/domain/appearance/`, guardrails en `tests/architecture/` con `design_system_audit.py` y `design_system_debt_baseline.json`. Solo hay 3 `setStyleSheet(` en `frontend/`. Esta línea es **verificar conformidad y cerrar huecos**, no construir un Design System nuevo.
- **Mercado Pago:** hoy es un método de pago **manual** (registra un pago ya confirmado con folio: `frontend/desktop/modules/sales_pos/dialogs/payment_dialog.py`), con `backend/infrastructure/integrations/mercadopago_credential_resolver.py` y `webhook_signature_verifier.py`. No hay integración con Orders API, Point ni Checkout. Esta línea es **construcción nueva** sobre caja, finanzas e idempotencia.

- **Activos:** la pipeline ASSET ya corrió; `docs/refactor/ASSET-24_validacion_final.md` deja **23 de 78 criterios sin cumplir**. Lo principal: las integraciones con Compras, RRHH, Inventario e impresión/PDF son solo Protocols sin adaptador; no hay outbox, auditoría, proyección financiera, MTBF/MTTR ni offline real. Ese documento dice que `modulos/activos.py` y `AssetService` siguen existiendo, pero en `16eb1d8e` ya no están: el cierre está desactualizado y todo debe re-verificarse en el código.
- **WhatsApp:** los archivos legacy del canal (`services/`, `integrations/`, `core/services/*whatsapp*`) ya no existen, pero `whatsapp_service/erp/bridge.py` (1060 líneas) **sigue abriendo la base SQLite del ERP directamente** (línea ~237). Eso contradice la regla central del prompt (WhatsApp no escribe tablas ERP) y es la brecha principal. Además, `CLAUDE.md` regla 9 manda preservar 3 shims de WhatsApp que ya no existen: registrar como contradicción y actualizar `CLAUDE.md`.
- **Repartos:** `ORD-30` deja pendientes: el módulo nuevo `frontend/desktop/modules/orders_delivery/` **no está conectado a la ventana principal** (cutover), faltan ~20 páginas de escritorio, la selección real de producto en "Nuevo pedido", el endpoint GPS de la PWA del repartidor y la verificación en dispositivo real; el cierre de WhatsApp-Delivery agrega el deep-link desde la notificación al pedido y la prueba E2E ERP+WhatsApp.

## Líneas de trabajo y orden

```
Línea A ── correcciones oleadas 0-2 ─────────────────────────────────────►
Línea B ── UI: conformidad del Design System (sin sesión/usuario) ───────►
Línea C ── (tras /sdlc-plan arquitectura) idempotencia/outbox, permisos,
           terminales, sesiones, caja y turno compartidos ──┐
                                                            ├─► correcciones oleadas 3-5
                                                            ├─► UI: usuario, sesión, logout
                                                            ├─► Línea D: Mercado Pago
                                                            └─► Línea E: WhatsApp (contratos ERP + HMAC)
Línea F ── Repartos: cutover del módulo nuevo y páginas faltantes ───────►
Línea G ── Activos: cerrar adaptadores, outbox, auditoría, proyección ───► (outbox/auditoría tras C)
```

| Orden | Línea | Contenido | Puede empezar |
|---|---|---|---|
| 1 | Plan | `/sdlc-plan arquitectura`, luego con `ui-ux.md` y `mercado-pago.md`, luego `correcciones.md` | Ya |
| 2 | A | Correcciones C-00, C-01, C-02, C-04, C-05, C-09 | Ya |
| 2 | B | UI: tokens y temas, QSS central, iconos, branding, densidades, PageViewport, tablas, diálogos, guardrails y pruebas visuales | Ya (solo `frontend/`, no choca con A si no tocan las mismas pantallas) |
| 3 | C | Ítems P0/P1 de arquitectura en su orden de dependencias | Al terminar la matriz de arquitectura |
| 4 | A/B | Correcciones C-03, C-06, C-07, C-08, C-10, C-11; UI de usuario, sesión, cambio de sucursal, bloqueo y logout | Cuando C entregue idempotencia, permisos y sesiones |
| 2 | F | Repartos: cutover de `orders_delivery` a la ventana principal, páginas faltantes, selección de producto | Ya (es UI y composición; verificar que no toque caja/finanzas) |
| 2 | G | Activos: adaptadores de RRHH, Compras, Inventario, impresión/PDF; MTBF/MTTR; QueryService de proyección financiera (lectura) | Ya |
| 4 | E | WhatsApp: sustituir el acceso SQLite de `erp/bridge.py` por clientes de API del ERP por bounded context con HMAC e identidad de servicio; inbox/outbox, handoff, consentimiento | Cuando C entregue la API interna (FastAPI), autenticación de servicio e idempotencia, y esté decidida la entrada pública de webhooks |
| 4 | G | Activos: outbox, auditoría, offline y consumo de eventos por Finanzas | Cuando C entregue outbox/auditoría y Finanzas tenga su contrato |
| 5 | D | Mercado Pago: contratos y puerto de pagos → Point → Checkout/QR → conciliación por consulta → caja → finanzas → WhatsApp/CRM → reembolsos | Cuando C entregue idempotencia, permisos, caja compartida y la decisión de dónde vive el backend |

**Regla para trabajar en paralelo:** dos ítems corren a la vez solo si no tocan los mismos archivos; usa una rama `sdlc/<id>` y un worktree por ítem.

## Decisiones del responsable que bloquean

1. **Entrada pública HTTPS única para webhooks (WhatsApp y Mercado Pago).** WhatsApp Cloud API solo entrega los mensajes entrantes por webhook, así que el endpoint público es obligatorio. El repo ya lo prevé: `whatsapp_service/service_host.py` escucha en `127.0.0.1` y documenta `0.0.0.0` solo detrás de proxy o túnel. Decisión: una PC anfitriona Windows encendida 24/7 expone **solo las rutas de webhook** (nunca la API completa ni PostgreSQL) mediante un túnel, y Mercado Pago usa la misma entrada. Opciones de túnel:
   - (a) ngrok gratuito: dominio fijo `*.ngrok-free.app` que no cambia al reiniciar; cuota mensual limitada (revisar contra el volumen real de mensajes y estados de WhatsApp).
   - (b) Cloudflare Tunnel: sin cuota de peticiones, pero requiere un dominio propio administrado en Cloudflare (costo anual del dominio).
   - (c) Servidor central de pago.
   En todos los casos: verificación de firma de cada proveedor, inbox durable antes de responder 200, y Mercado Pago conserva la **conciliación por consulta** como red de seguridad cuando el túnel o la PC anfitriona caen. El token de Mercado Pago vive cifrado en la PC anfitriona (servicio local), nunca en las cajas.
2. Todas las preguntas abiertas de `correcciones.md` (falla del motor de precios, venta de estimados, volumen vs. precio negociado, política de despiece por destino, reconstrucción por kg).
3. Si existe un prompt maestro de Repartos, agregarlo como `inputs/repartos.md`; si no, los pendientes de ORD-30 son la referencia.
4. Las que agregue `/sdlc-plan arquitectura` (precedencia rol/usuario, vigencia offline, PC anfitriona del servicio local).
