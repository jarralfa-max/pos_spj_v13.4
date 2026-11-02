# SDLC-PAY-003 — La referencia del procesador se pierde en Caja, Finanzas y ticket: conciliación por operación imposible

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 9 · Fase 10 · Fase 12.3 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 1.2 «Referencia externa en asignaciones de Caja» (`defectuoso`), Fase 1.1 «Ticket imprime referencia» (`ausente`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-002

## Problema
Aunque el cajero capture la referencia del pago, Caja agrupa los pagos por método y la descarta (salvo vales), así que `payment_allocations.external_reference` queda vacío. El evento hacia Finanzas sólo lleva método e importe y el ticket sólo imprime la forma de pago. Ninguna liquidación o reclamo puede casarse con la venta.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/integrations/sales_cash_effects_client.py:139-148` — `_payment_lines` agrupa y descarta `reference` (*verificado directamente*)
- `migrations/standalone/175_cash_register_bounded_context_schema.py:73-74` — columna `external_reference` y UNIQUE existen; `sales_integration.py:45-57` la lee
- `backend/application/sales/use_cases/checkout_use_cases.py:318` — payload a Finanzas sin referencia
- `backend/infrastructure/printing/ticket_layout_renderer.py:279-283`; `sale_ticket_escpos_renderer.py:36-38` `PAYMENT_LABELS` sin uso
- Prueba: ninguna

## Impacto
Finanzas y tesorería no pueden conciliar cobros MP/tarjeta por operación; el cliente no tiene comprobante con la referencia.

## Objetivo
- Cada pago electrónico conserva su referencia en `payment_allocations.external_reference` (una asignación por pago, no por método).
- El evento de pago hacia Finanzas incluye la referencia y queda en la línea del asiento.
- El ticket imprime la referencia enmascarada según política; se elimina el mapa de etiquetas muerto.
- Pruebas de punta a punta: venta MP → Caja → Finanzas → ticket conservan la referencia.

## Alcance
- **Incluye:** Cliente de efectos de Caja, payload de Finanzas, renderizadores de ticket, pruebas.
- **No incluye:** Cortes X/Z (PAY-005); conciliación de liquidaciones (PAY-019).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Ninguno además de la matriz.

## Preguntas abiertas
- Ninguna por ahora.
