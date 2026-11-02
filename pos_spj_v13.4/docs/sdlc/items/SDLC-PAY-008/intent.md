# SDLC-PAY-008 — La venta se completa sin pago verificado: estado «esperando pago» muerto y puntos acumulados sobre pagos no confirmados

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 4.3 · Fase 11 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 3 «Estado de venta esperando pago» (`parcial`) y Fase 11 «Puntos sólo con pago confirmado» (`defectuoso`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-007

## Problema
`SaleStatus.PAYMENT_PENDING`, `Sale.mark_payment_pending()` y el evento `PAYMENT_PENDING` existen pero nadie los usa: toda venta pasa de cobro a COMPLETED en el mismo clic. Por eso inventario, Caja, Finanzas y Fidelidad reaccionan antes de saber si el pago electrónico se aprobó; un pago rechazado o nunca hecho genera puntos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/domain/sales/enums.py:10`; `backend/domain/sales/entities.py:393` sin llamadores; `backend/domain/sales/events.py:30` nunca emitido
- `backend/application/loyalty/integrations/sales_events.py:39-55` — puntos con `SALE_COMPLETED`
- `backend/domain/loyalty/policies/accrual_policy.py:43-50` — MP no está en `DEFERRED_TENDERS` (*verificado directamente*)
- Prueba: ninguna

## Impacto
Clientes con puntos por compras no pagadas; efectos financieros e inventario comprometidos antes de la aprobación.

## Objetivo
- Una venta con porción electrónica pendiente queda en `PAYMENT_PENDING` hasta que la intención se apruebe; sólo entonces se completa.
- Rechazo, cancelación o expiración regresan la venta a cobro sin efectos financieros ni puntos.
- Se decide y prueba qué se compromete durante la espera (reserva de inventario sí/no).
- Pruebas: aprobado, rechazado, expirado y aprobación tardía.

## Alcance
- **Incluye:** Ciclo de vida de la venta, checkout, consumidores de eventos, pruebas.
- **No incluye:** UI de espera (PAY-013); pagos mixtos (PAY-016).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria SALES / ERP Fase 7 (reserva de inventario sólo en ventas suspendidas).

## Preguntas abiertas
- ¿Qué se compromete mientras el pago está pendiente: inventario reservado sí, puntos y caja no?
