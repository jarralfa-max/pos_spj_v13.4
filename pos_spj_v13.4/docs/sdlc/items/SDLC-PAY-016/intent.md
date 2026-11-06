# SDLC-PAY-016 — Pagos mixtos con porción electrónica: sin compensación si falla y montos capturados vía float

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 9.3 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 9.3 «Pagos mixtos con Decimal» (`parcial`) y «Compensación si falla una porción» (`ausente`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-008

## Problema
Cada pago de un cobro mixto se guarda en su propia unidad de trabajo; si una porción falla, las anteriores quedan registradas y el cajero debe anularlas a mano. La regla es `total_paid >= total` sin redondeo explícito, y `MoneyInput` convierte desde float.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/sales_pos/dialogs/payment_dialog.py:344-357`
- `backend/domain/sales/policies/payment_policy.py:36,42`
- `frontend/desktop/components/numeric_input.py:25-26` — `Decimal(str(float))`
- Prueba: `tests/unit/test_sales_payment.py:95,177,286`; `tests/integration/sales/test_sales_audit_cebf67a.py:173,187`

## Impacto
Cobros parciales que no cubren la venta; posibles diferencias de centavos.

## Objetivo
- `Sum(asignaciones) = TotalDue` con redondeo Decimal explícito; captura sin float.
- Si la porción electrónica falla, la venta no se completa y la compensación de lo ya registrado es explícita; un pago electrónico aprobado nunca se borra.
- Fidelidad evalúa elegibilidad por componente.
- Pruebas: 500 = 200 efectivo + 300 MP con éxito, rechazo y aprobación tardía.

## Alcance
- **Incluye:** Política de pagos, diálogo, `MoneyInput`, pruebas.
- **No incluye:** Redondeo de totales de venta (SDLC-SALES-002).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SALES-002 (redondeo de totales).

## Preguntas abiertas
- Ninguna por ahora.
