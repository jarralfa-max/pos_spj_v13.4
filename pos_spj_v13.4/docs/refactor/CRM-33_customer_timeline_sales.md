# CRM-33 — Customer Timeline: se incorpora Ventas (SALE_COMPLETED/CANCELLED)

Fecha: 2026-08-16. Sexta fase del cut-over completo (mapa Fase 0 §4
"Customer Timeline").

## Hallazgo

A diferencia de crédito/consentimiento/navegación, la Timeline en sí YA
existía y estaba completamente wireada: `CustomerHistoryQueryService`
(CRM-12, `backend/application/customers/queries/`) agrega
`customer_audit_log` + `crm_audit_log` (vía oportunidades) +
`customer_service_audit_log` (vía casos) + `customer_credit_audit_log` +
`customer_privacy_audit_log` en un solo feed cronológico, ya renderizado
sin cambios adicionales en la pestaña "Auditoría" del Expediente
(`customer_profile_page.py`, genérico: `[fecha, módulo, acción]` para
cualquier `source_module` que llegue).

Lo que faltaba, comparado con la lista explícita del prompt maestro
(`SALE_COMPLETED`, `CREDIT_GRANTED`, `PAYMENT_RECEIVED`, etc.): **Ventas
no contribuía ninguna entrada**. Mismo patrón de identidad no migrada que
el resto de esta sesión — `ventas.cliente_id` es la identidad legacy,
nunca `customers.id`.

## Qué se construyó

- `CustomerHistoryQueryService._sales_entries(customer_id)`: resuelve
  `customer_id` → `customers.legacy_customer_id` (bridge CRM-21), lee
  `ventas WHERE cliente_id=?` con ese id legacy, y produce una entrada
  `VENTA_COMPLETADA` (o `VENTA_CANCELADA` si `estado` es cancelada/
  cancelado) por cada venta — mismo patrón de "ausencia de bridge = sin
  contribución, no error" que `_table_exists` ya usa para las demás
  fuentes.
- Cero cambios de UI — la pestaña "Auditoría" ya renderiza cualquier
  `source_module` genéricamente; las ventas simplemente empiezan a
  aparecer.
- `tests/integration/customers/conftest.py`: se agregó una tabla `ventas`
  mínima a `_LEGACY_OPS_DDL` (mismo criterio de "forma legacy real,
  solo lectura" que las tablas `clientes`/`pedidos_whatsapp`/
  `delivery_orders` que esa fixture ya tenía).

## Explícitamente NO tocado en esta fase

- Pagos/cobros (`cuentas_por_cobrar`) — ya cubierto indirectamente vía
  `credit_summary` en otra pestaña del Expediente, no vía la Timeline;
  agregarlo a la Timeline específicamente es una extensión futura de bajo
  riesgo, mismo patrón, no incluida aquí para mantener esta fase acotada.
- WhatsApp/Delivery en la Timeline — mismo patrón aplicable
  (`pedidos_whatsapp`/`delivery_orders`, ya legibles read-only por otras
  queries de CRM-13), no incluidos en esta pasada.
- Un mecanismo de eventos de dominio/integración en tiempo real (lo que
  el prompt maestro sugiere con `SALE_COMPLETED` como nombre de evento) —
  esta Timeline sigue siendo un query de agregación bajo demanda sobre
  audit logs existentes, no un event bus de integración nuevo. Construir
  ese bus es una iniciativa mucho mayor (tocaría Ventas, WhatsApp,
  Finanzas emitiendo eventos reales) fuera de alcance de una fase de
  lectura.

## Verificación

```bash
python -m pytest tests/integration/customers/test_customer_360_application.py \
  tests/architecture/test_customers_crm_*.py -v
```
40 tests pasando (3 nuevos de esta fase + 37 preexistentes, cero
regresiones; el guardrail `test_customers_crm_has_no_integer_identity`
detectó correctamente un nombre de variable local (`legacy_id`, token
explícitamente prohibido por REGLA CERO) — renombrado a
`legacy_customer_id` (la forma ya usada en todo el resto del código), sin
cambio de comportamiento).
