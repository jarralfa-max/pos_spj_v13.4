# SDLC-WA-021 — El precio y la existencia guardados en la conversación se vuelven el precio de registro del pedido

- **Prioridad:** P0
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §31, §33, §34 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-003

## Problema
La sesión guarda copias de producto con precio y existencia (`_producto_temp`, `pedido_items.precio_unitario`) y calcula subtotales y totales con ellas. Al confirmar, ese precio cacheado se manda al ERP como precio del pedido (API) o se escribe con el total calculado en el respaldo SQLite. El catálogo es SQL propio del canal (solo lista base más precio por sucursal; ignora listas por cliente), la existencia se calcula en el canal y el stock se valida contra la foto vieja. Un cambio de precio entre la consulta y la confirmación no se refleja.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/models/context.py:43-132` (`:50,53-54,122-123`); `state/conversation.py:84-110`
- `whatsapp_service/flows/pedido_flow.py:104,155-161`
- `whatsapp_service/application/confirm_order_use_case.py:53-59` → `erp/bridge.py:433-439` (API) y `:470,494-501` (SQLite con total)
- `whatsapp_service/erp/catalog_sql.py:35-68` — precio y existencia propios
- `whatsapp_service/flows/cotizacion_flow.py:96,114`; `flows/repetir_flow.py:127`; `erp/bridge.py:698,715` — totales en el canal
- Dueños sin uso: `backend/application/pricing/queries/product_price_query_service.py`; `backend/application/orders_delivery/use_cases/capture_order_use_cases.py:99` (tarifica en el servidor)
- Prueba: ninguna cubre precio cambiado entre consulta y confirmación

## Impacto
Dinero: se cobra o se promete un precio distinto al vigente; existencia sobrevendida.

## Objetivo
- La conversación guarda solo referencias (producto, cantidad, unidad); precio, existencia y totales los calcula el dueño al confirmar.
- El pedido se crea por el caso de uso de Orders, que tarifica en el servidor; el canal muestra el resumen que devuelve.
- Prueba: precio cambiado entre consulta y confirmación se cobra al precio vigente y se avisa al cliente.

## Alcance
- **Incluye:** Contexto de pedido y cotización, catálogo vía consultas del ERP, confirmación.
- **No incluye:** Contrato REST del ERP en sí (SDLC-WA-003); unidades (SDLC-WA-030).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-WA-003; SDLC-ORD-003 (pipeline de pedidos autoritativo).

## Preguntas abiertas
- Depende de la respuesta abierta de SDLC-ORD-003/SDLC-WA-003: ¿el pedido de WhatsApp nace en `customer_orders` (Orders/Delivery) o en `ventas` estado `pendiente_wa`?
