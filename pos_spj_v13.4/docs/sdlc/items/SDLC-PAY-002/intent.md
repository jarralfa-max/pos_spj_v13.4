# SDLC-PAY-002 — Un mismo pago de Mercado Pago puede respaldar varias ventas: referencia opcional, libre y no única

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 3 · Fase 4.4 · Fase 19 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 1.1 «Pago MP verificado…» (`defectuoso`) y «Referencia de pago única entre ventas» (`ausente`))
- **Estado:** borrador
- **Depende de:** —

## Problema
Hoy un cobro con Mercado Pago es una declaración del cajero: cobra fuera del sistema y registra el pago como confirmado. La referencia es opcional y de texto libre, y `sale_payments.reference` no tiene restricción de unicidad. El mismo pago (o ninguno) puede registrarse en dos o más ventas; cada una se completa, Caja la cuenta, Finanzas la asienta y Fidelidad acumula puntos. Es una contención inmediata mientras no exista integración real.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/sales_pos/dialogs/payment_dialog.py:194-196` aviso «registra un pago ya confirmado…» (*verificado directamente*); referencia opcional `:107,:260`
- `backend/infrastructure/db/schema/sales_schema.py:117-125` — `sale_payments` sin UNIQUE en `reference` (*verificado directamente*)
- `backend/application/sales/use_cases/payment_use_cases.py:56-130` — no valida referencia ni duplicados
- `backend/application/sales/use_cases/checkout_use_cases.py:142` — emite `PAYMENT_CONFIRMED` sin verificación externa
- Prueba: `tests/unit/test_sales_payment.py:309` fija MP con referencia completándose directo; duplicados: ninguna

## Impacto
Cajero, gerente y Finanzas: ventas cobradas una vez y registradas como pagadas varias veces, o nunca cobradas. Pérdida directa de dinero y de inventario; ocurre en cualquier cobro MP o tarjeta manual.

## Objetivo
- Un pago `MERCADO_PAGO` exige referencia no vacía con formato validado en el caso de uso (no sólo en el diálogo).
- Una referencia de procesador no anulada no puede aparecer en dos pagos (restricción en BD + error de dominio claro), compatible con anulaciones y con el DELETE+INSERT actual del repositorio.
- Prueba: registrar la misma referencia en dos ventas falla la segunda; anular y volver a registrar funciona.
- Se mide sobre una copia de la BD real cuántas referencias vacías o repetidas existen y la migración no rompe esos datos.

## Alcance
- **Incluye:** Caso de uso de pago, esquema `sale_payments` (migración), mensaje en el diálogo, pruebas.
- **No incluye:** Verificación contra la API (PAY-008/PAY-011); propagación a Caja/Finanzas (PAY-003); idempotencia por `operation_id` (SDLC-ARQ-IDEM-001).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-ARQ-IDEM-001 (operation_id por clic), SDLC-ARQ-IDEM-003 (DELETE+INSERT de hijos; pagos revertidos siguen CONFIRMED) — coordinar el índice con ambos.

## Preguntas abiertas
- ¿La referencia también es obligatoria y única para Tarjeta (número de autorización) y Transferencia?
- ¿Qué se hace con ventas históricas con referencia vacía o repetida (se miden sobre copia)?
