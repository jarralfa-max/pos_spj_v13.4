# SDLC-ORD-009 — Pedidos/Delivery nunca se validó de punta a punta en entorno real (PWA en dispositivo, PyQt5 real, ERP+WhatsApp)

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/refactor/ORD-30_validacion_final.md` → "Pendiente" §5 (verificación manual de la PWA en navegador o dispositivo y de las páginas en PyQt5 real) y `docs/WHATSAPP_DELIVERY_CLOSEOUT_STATUS.md` → "Recomendación" §3 (smoke E2E documentado por flujo: mostrador, reparto, programado, cotización→venta, ajuste fuera de tolerancia). Re-verificado (`/sdlc-plan` Modo B, 2026-10-31).
- **Estado:** borrador
- **Depende de:** SDLC-ORD-004 (sin descuento de inventario el smoke falla por diseño); para los flujos de WhatsApp, SDLC-WA-003 y SDLC-WA-005

## Problema
Todo lo que se dio por cerrado en Pedidos/Delivery se probó con SQLite en memoria y Qt sin pantalla. Nadie ha recorrido los flujos con la app real, la PWA en un teléfono y el microservicio de WhatsApp conectados. ORD-30 dice que no hay una suite e2e separada, y el cierre de WhatsApp lo deja como pendiente de cierre al 100%. La sonda de esta corrida mostró que las pruebas unitarias e integradas no detectan defectos de punta a punta: con 405 pruebas verdes, un pedido completado no descuenta inventario (SDLC-ORD-004).

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado directamente el 2026-10-31 sobre `ed026f7b`.

- `ls tests/e2e | grep -iE "order|deliver|pedido|whats"`: sin resultados. No hay e2e de Pedidos ni de WhatsApp.
- Grep de `playwright|selenium|jsdom` en `tests/`: cero. Ninguna prueba ejecuta la PWA (`frontend/web/delivery/*.js`).
- Suite curada (`tests/unit/test_orders_delivery_*.py`, `tests/integration/test_orders_delivery_*.py`, `tests/architecture/test_orders_delivery_permissions_are_granular.py`): `405 passed in 25.61s`. ORD-30 reportó 418 porque incluía `tests/*/logistics/`, que no se corrió aquí.
- Flujos del cierre WA con bloqueo conocido: los pedidos y cotizaciones de WhatsApp no pueden crearse en producción (SDLC-WA-003), y los avisos del microservicio no llegan a la bandeja del POS (SDLC-WA-005).
- Las 23 rutas de escritorio ya tienen página real (`frontend/desktop/modules/orders_delivery/orders_delivery_routes.py:21-54`, comprobado: 23 de 23 en `_REAL_ROUTE_BUILDERS`). La "Parcial deliberada" de ORD-28 quedó cerrada, pero sin verificación visual.

## Impacto
Defectos de integración entre Pedidos, Ventas, Inventario, Caja y WhatsApp llegan a producción sin que ninguna prueba los vea. El responsable no tiene un guion para aceptar el módulo.

## Objetivo
- Hay un guion de smoke E2E versionado por flujo (mostrador/pickup, reparto con PWA, programado, cotización→pedido→venta, ajuste de peso fuera de tolerancia y su aprobación) con resultado esperado en pedido, venta, inventario, caja y avisos.
- Se ejecuta sobre una copia de la base real con la app de escritorio, la PWA en un dispositivo o navegador real y el microservicio local. La evidencia (capturas, salidas) queda en `docs/sdlc/items/SDLC-ORD-009/`.
- Los flujos automatizables quedan como prueba e2e en `tests/e2e/` contra SQLite real, incluido el balance de inventario al final.
- Cada defecto encontrado entra al backlog como ítem propio y no se arregla dentro de este ítem.

## Alcance
- **Incluye:** Guion, ejecución, prueba e2e automatizable y registro de hallazgos.
- **No incluye:** Corregir lo que se encuentre (ítems nuevos).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; nunca sobre un `.db` real, solo una copia en el directorio temporal; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
`docs/refactor/ORD-30_validacion_final.md`; `docs/WHATSAPP_DELIVERY_CLOSEOUT_STATUS.md`; memoria Compras ("'no pasa nada' = feedback invisible, verificar UI con screenshot sobre copia de la base real"); SDLC-ARQ-TEST-001 (pruebas de aceptación de la arquitectura).

## Preguntas abiertas
- ¿Hay un teléfono o dispositivo de repartidor disponible para la prueba, o basta un navegador móvil emulado?
- ¿El canal WhatsApp está activo en alguna sucursal? Si no, ¿los flujos WA se dejan fuera del primer smoke? (Misma pregunta abierta de SDLC-WA-003.)
