# SDLC-ORD-003 — Decisión: pipeline autoritativo de pedidos y plan de corte

- **Estado:** decisión registrada (2026-11-06), lote 6. La implementación del corte queda en ítems posteriores, como fija el intent.
- **Regla del responsable** (respuesta en `intent.md`, 2026-11-05): «el que esté más avanzado».

## Decisión
El pipeline autoritativo es el canónico de Pedidos/Delivery: `customer_orders`, sus líneas, `delivery_jobs` y el resto del esquema de `orders_delivery_schema.py`, con `quotes` para cotizaciones. Un pedido de WhatsApp debe nacer en `customer_orders` (vía `CaptureOrderUseCase`, o `CreateCustomerOrderUseCase` con `quote_id` si viene de una cotización aceptada). No debe nacer en `ventas` con estado `pendiente_wa`, ni en `delivery_orders`, ni en `cotizaciones`.

Esto responde también la pregunta que bloquea SDLC-WA-021 («¿el pedido de WhatsApp nace en `customer_orders` o en `ventas` `pendiente_wa`?»): nace en `customer_orders`.

## Por qué es el más avanzado (medido en la rama `fix/lote-6`)
| Criterio | Canónico (`customer_orders`/`quotes`) | WhatsApp legacy (`ventas` `pendiente_wa`, `delivery_orders`, `cotizaciones`) |
|---|---|---|
| Modelo | Dominio, casos de uso, permisos granulares, auditoría y outbox (`backend/*/orders_delivery`) | SQL directo desde el microservicio (`whatsapp_service/erp/bridge.py:475-1039`, `erp/adjustment_approval.py:85-119`) |
| Inventario | Reserva de saldos reales y descuento al despachar o entregar, con reverso (SDLC-ORD-004) | Sin descuento canónico |
| Dinero | Venta proyectada, Caja en la transacción, efectivo de repartidor en el mayor (SDLC-ORD-001) | `ventas.total` escrito a mano, sin asiento |
| Precio | Pricing en el servidor (`CaptureOrderUseCase`), y el precio cotizado sólo con `quote_id` (SDLC-ORD-005) | Precio del microservicio |
| Pruebas | 65 archivos `test_orders_delivery_*` y `tests/integration/orders_delivery/*` | Pruebas del microservicio, sin cruzar el ERP canónico |
| Pantallas | 23 de 23 rutas de escritorio y PWA del repartidor | Ninguna pantalla de escritorio lee `pendiente_wa` |

## Lo que todavía lee o escribe lo legacy
Medido con grep, sin contar pruebas:
- **Escriben `delivery_orders`:** `whatsapp_service/erp/adjustment_approval.py:119` y `backend/application/use_cases/settle_delivery_driver_use_case.py:135`. El segundo no tiene llamadores (SDLC-CORE-005).
- **Leen `delivery_orders`:**
  - `backend/application/customers/queries/customer_delivery_summary_query.py:67-77`, el expediente del cliente. Por eso los pedidos del escritorio no aparecen en él.
  - `backend/application/queries/driver_settlement_query_service.py:39`.
- **Escriben `ventas` `pendiente_wa` y `cotizaciones`:** `whatsapp_service/erp/bridge.py:479,488,701,710`. Los leen `whatsapp_service/router/delivery_router.py:130` y `webhook/mercadopago.py:119`.

## Plan de corte (ítems posteriores, en este orden)
1. **Congelar lo legacy.** Hecho en este lote: `tests/architecture/test_orders_single_pipeline_ratchet.py` impide que aparezca en el ERP un lector o escritor nuevo de `delivery_orders` (la lista sólo puede encogerse).
2. **Expediente del cliente** (ampliación de este ítem, SDLC-CRM-003): `customer_delivery_summary_query` lee `customer_orders` por `customer_id`. Lo pendiente es el puente `clientes.id`/`customers.id` de CRM-21.
3. **Pedido de WhatsApp a `customer_orders`** (SDLC-WA-003 y SDLC-WA-021): el puente del microservicio llama a la API o caso de uso canónico en vez de `INSERT INTO ventas … 'pendiente_wa'`. Lo mismo vale para `cotizaciones`, que pasa a `quotes`.
4. **Ajustes de peso** (`adjustment_approval.py`): se reemplazan por `AcceptCustomerAdjustmentUseCase` y `RejectCustomerAdjustmentUseCase` sobre `customer_orders`.
5. **Liquidación legacy:** retirar `settle_delivery_driver_use_case.py` y `driver_settlement_query_service.py` (SDLC-CORE-005). La canónica ya asienta (SDLC-ORD-001).
6. **Retiro de tablas:** cuando la guardia llegue a cero lectores y escritores, se migran los datos que queden y se borran `delivery_orders`, `pedidos_whatsapp*` y el estado `pendiente_wa`. Se prueba sobre una copia de la base.

## Preguntas abiertas
- Ninguna nueva. El orden de los pasos 2 a 5 lo fija la dependencia de cada ítem en el backlog.
