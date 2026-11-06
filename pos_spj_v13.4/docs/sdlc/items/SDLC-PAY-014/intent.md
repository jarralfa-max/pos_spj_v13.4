# SDLC-PAY-014 — Checkout Pro y enlaces de pago: no se generan desde el ERP; el microservicio tiene dos versiones sin idempotencia

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 5 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 5 «Checkout Pro / enlace…» (`ausente en ERP; duplicado en WA`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-009

## Problema
El ERP no genera órdenes digitales ni enlaces de pago vinculados a una venta o pedido. El microservicio tiene dos constructores de preferencias duplicados, sin clave de idempotencia ni registro del id de la preferencia, y cada clic crea un enlace nuevo pagable.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `whatsapp_service/flows/pago_flow.py:46-47,74-123`
- `whatsapp_service/infrastructure/providers/mercadopago/gateway.py:6-15,42-82` (reconoce la duplicación)
- `frontend/desktop/modules/sales_pos/dialogs/payment_dialog.py:194-196` — «La liga de cobro no se genera aquí»
- Prueba: `whatsapp_service/tests/test_mercadopago_gateway.py:43-87` (gateway sin uso)

## Impacto
Ventas remotas sin conciliación automática; riesgo de cobro doble por enlaces repetidos.

## Objetivo
- El backend crea una orden digital por intención con referencia externa estable, vigencia y URL devuelta sólo al cliente autorizado.
- Recrear una orden vencida es explícito, trazable e idempotente; nunca hay dos enlaces activos para la misma intención.
- Sin tokens en URLs; pruebas con proveedor falso.

## Alcance
- **Incluye:** Caso de uso, adaptador, persistencia, pruebas.
- **No incluye:** QR (PAY-015); envío por WhatsApp (PAY-025).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Ninguno además de la matriz.

## Preguntas abiertas
- Ninguna por ahora.
