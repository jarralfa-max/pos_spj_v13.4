# SDLC-PAY-024 — Operaciones de pago sin auditoría: el registro de auditoría de Ventas existe y nadie lo llama

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 12.3 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 12.3 «Auditoría de operaciones de pago» (`ausente`))
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-AUD-002, SDLC-PAY-007

## Problema
`record_sales_audit_entry` y `SalesAuditEntry` tienen los campos necesarios pero no tienen llamadores. Un cobro sólo deja una fila en el outbox de ventas, sin estación ni estado anterior/nuevo ni evidencia de autorización.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sales/audit.py:11` sin llamadores
- `backend/domain/sales/value_objects/sales_audit_entry.py:31-43`
- `backend/application/sales/use_cases/payment_use_cases.py:126-129` — sólo outbox
- Prueba: ninguna

## Impacto
Sin rastro para investigar cobros, cancelaciones o reembolsos.

## Objetivo
- Cada operación de pago (crear, confirmar, cancelar, reembolsar, conciliar, asignar terminal, cambiar credencial) audita usuario, fecha, sucursal, estación, importe, moneda, proveedor, referencia enmascarada, estado anterior/nuevo, autorización y correlation id.
- Nunca datos de tarjeta ni CVV.
- Pruebas.

## Alcance
- **Incluye:** Escritor de auditoría en casos de uso de pago, pruebas.
- **No incluye:** Esquema común de auditoría (SDLC-ARQ-AUD-002).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-ARQ-AUD-002.

## Preguntas abiertas
- Ninguna por ahora.
