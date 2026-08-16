# CRM-38 — Fase 4: Timeline incorpora actividades/tareas/notas directas y pedidos WhatsApp

Fecha: 2026-08-16. Continuación del cut-over a petición del usuario de
retomar "FASE 4 — CUSTOMER TIMELINE".

## Punto de partida (no se repite trabajo de CRM-33)

La Timeline (`CustomerHistoryQueryService`, CRM-12) ya agregaba
`customers`/`crm` (vía oportunidades)/`customer_service`/
`customer_credit`/`customer_privacy` desde CRM-12, y `ventas` desde
CRM-33. Es decir: creación/edición/activación/suspensión/bloqueo/
reapertura, crédito completo (solicitud→aprobación→suspensión→cierre) y
ventas YA estaban cubiertos antes de esta fase — no se reconstruyó nada
de eso.

## Hallazgo: actividades/tareas/notas SÍ son correlacionables directamente

`_crm_entries` (CRM-12) solo correlaciona `crm_audit_log` vía
`opportunities.customer_id` — deja fuera cualquier actividad/tarea/nota
que no esté colgada de una oportunidad. Pero el esquema ya soporta
correlación directa: `CRMRelatedEntityType.CUSTOMER` existe exactamente
para esto — un Activity/Task/Note puede apuntar a un cliente sin pasar
por un Lead/Opportunity. Confirmado que el enum lo permite, que
`crm_audit_log` tiene columnas `activity_id`/`task_id`/`note_id`
directamente, y que los tres casos de uso de creación
(`CreateCRMActivityUseCase`/`CreateCRMTaskUseCase`/`CreateCRMNoteUseCase`)
ya aceptan `related_entity_type="CUSTOMER"` sin ningún cambio de código —
solo faltaba que la Timeline los leyera.

## Qué se construyó

- **`_crm_direct_entries`**: mismo criterio que `_crm_entries`, pero
  filtra `crm_activities`/`crm_tasks`/`crm_notes` por
  `related_entity_type='CUSTOMER' AND related_entity_id=customer_id`
  directamente, sin pasar por oportunidades.
- **`_whatsapp_order_entries`**: `pedidos_whatsapp` correlacionado vía el
  mismo patrón de bridge legacy que `_sales_entries` (CRM-33) — extraído
  a un helper compartido `_legacy_customer_id()` para no duplicar la
  consulta entre ambos.

## Explícitamente NO tocado en esta fase (con razón)

- **Devoluciones**: no existe una tabla de devoluciones separada de
  `ventas` en este esquema — una devolución se modela como una venta
  cancelada/reversada (`VENTA_CANCELADA`, ya cubierto por CRM-33). No hay
  un evento "DEVOLUCION" distinto que agregar.
- **Pagos/cobros**: `cuentas_por_cobrar` no tiene una tabla de pagos
  separada — cada fila de CxC solo guarda un único `fecha_pago`,
  perdiendo el historial si hubo pagos parciales múltiples. Agregar esto
  a la Timeline con la fidelidad que un evento "PAYMENT_RECEIVED" merece
  requeriría antes mejorar el propio modelo de datos de pagos — no se
  fuerza un evento de baja calidad solo por completar la lista.
- **Cambios de segmento**: `crm_audit_log` no registra cambios de
  membresía de segmento con una acción distinguible hoy — no se fabricó
  una entrada sin datos reales detrás.
- **Bus de eventos de dominio/integración en tiempo real** (lo que el
  prompt maestro sugiere con los nombres `SALE_COMPLETED`,
  `PAYMENT_RECEIVED`, etc.): la Timeline sigue siendo un query de
  agregación bajo demanda sobre audit logs ya existentes, no una
  suscripción a eventos en vivo — mismo alcance que CRM-33, sin cambios.

## Verificación

```bash
python -m pytest tests/integration/customers/test_customer_360_application.py \
  tests/architecture/test_customers_crm_*.py -v
```
46 tests pasando (6 nuevos de esta fase), cero regresiones. Dos ajustes
de nombre de acción durante la escritura de pruebas (`CRM_ACTIVITY_CREATED`/
`CRM_NOTE_CREATED`, no los nombres sin prefijo que asumí inicialmente) y
un parámetro requerido (`due_at` en `CreateCRMTaskUseCase`) — ambos
hallazgos de la prueba, no cambios de comportamiento de producción.
