# Mercado Pago — Plan de pruebas (TEST_PLAN)

- **Ítem:** SDLC-PAY-001 · **Fecha:** 2026-11-09
- **Contexto:** [TRD](MERCADO_PAGO_INTEGRATION_TRD.md)
- **Reglas:**
  - ninguna prueba automatizada envía pagos reales;
  - el adaptador se prueba con `httpx.MockTransport` (ADR-MP-004) y con fakes del `PaymentProviderPort`;
  - el sandbox no se toma como réplica del Point físico;
  - `QApplication` sólo como fixture de módulo.

## 1. Pruebas ya escritas (`fix/lote-4`)

| Archivo | Cubre |
|---|---|
| `tests/unit/test_sales_payment_reference.py` | PAY-002: obligatoria y formato por método, única entre ventas, mayúsculas y espacios, mismo número en otro método, DELETE+INSERT, anular o cancelar libera, carrera resuelta por el índice, migración 384 con y sin duplicados |
| `tests/unit/test_pos_checkout_dialogs.py::test_el_dialogo_no_agrega_un_pago_con_referencia_rechazada` | PAY-002 en el diálogo |
| `tests/integration/sales/test_payment_reference_traceability.py` | PAY-003: asignación por pago con referencia, línea del asiento, ticket enmascarado (ESC/POS y HTML), traductor con eventos viejos |
| `tests/integration/finance/test_processor_account_mirror.py` | PAY-004: venta, devolución y compra al mismo espejo; balanceado; sin cuenta o con dos, falla a la vista; alta de una segunda cuenta rechazada; migración 385 |
| `tests/integration/cash_register/test_cut_payment_breakdown.py` | PAY-005: desglose por medio con venta mixta, documento impreso, clasificación de vales, crédito y otros |

## 2. Unitarias por ítem futuro

| Ítem | Casos |
|---|---|
| PAY-007/008 | Transiciones válidas e inválidas de `PaymentIntent`; sólo hacia adelante; idempotencia por `operation_id`; Decimal y redondeo; la venta no se completa sin `APPROVED` |
| PAY-009 | Mapeo de estados externos (tabla ACL); `X-Idempotency-Key` estable en el reintento; mapeo de errores HTTP (401, 404, 409, 429, 5xx, timeout) |
| PAY-016 | Plan mixto; compensación de la porción fallida |
| PAY-018 | Comisión, IVA de comisión y neto; el depósito no duplica ingreso |
| PAY-023 | Cada operación exige su permiso en el caso de uso |

## 3. Integración y seguridad

- **Inbox:** se persiste antes de 200; duplicado idempotente; reintento con backoff; `DEAD` con alerta.
- **Firma:** inválida, ausente, `ts` fuera de ventana, replay, payload manipulado, cuenta receptora ajena,
  monto o moneda distintos.
- **Credenciales:** token caducado, credencial faltante, logs sin secretos (SDLC-SEC-006).
- **Ámbito:** acceso cruzado entre sucursales y entre empresas; reembolso sin permiso; importe modificado
  a mano.
- **Contextos:** Caja, Finanzas y Fidelidad (puntos sólo con el pago confirmado), con la composición real
  del POS, como `test_sales_checkout_settles_everything.py`.

## 4. Los 20 escenarios de fallo y concurrencia (§16.4 → PAY-027)

| # | Escenario | Ítem | Expectativa |
|---|---|---|---|
| 1 | Dos cajeros, misma terminal | PAY-012 | El segundo se rechaza antes de llamar al proveedor |
| 2 | Timeout al crear la orden | PAY-009/011 | `UNKNOWN`; la consulta usa la misma intención |
| 3 | Orden creada, respuesta perdida | PAY-011 | Se recupera por `external_reference` sin crear otra |
| 4 | Pago aprobado sin internet en la caja | PAY-011/017 | Se resuelve al volver la red, una sola vez |
| 5 | Webhook duplicado | PAY-010 | Un solo efecto |
| 6 | Webhook fuera de orden | PAY-010 | Nunca retrocede |
| 7 | Webhook nunca recibido | PAY-011 | La consulta lo resuelve |
| 8 | Reinicio del POS durante el pago | PAY-013 | El diálogo retoma la intención |
| 9 | Reinicio del backend o receptor | PAY-010 | El inbox conserva lo recibido |
| 10 | Caída de PostgreSQL | ARQ-HYB | El POS sigue con SQLite; nada se pierde |
| 11 | Falla la sincronización | ARQ-HYB | Reintento sin duplicar |
| 12 | Reintento tras aprobación | PAY-009 | Misma llave, sin doble cobro |
| 13 | Cambio de importe con pago pendiente | PAY-008 | Se bloquea la edición de la venta |
| 14 | Reembolso parcial y luego otro | PAY-006/020 | No excede lo cobrado |
| 15 | Pago mixto con éxito parcial | PAY-016 | Compensación |
| 16 | Contracargo tras conciliar | PAY-021 | Asiento de contracargo, sin tocar la venta |
| 17 | Enlace vencido | PAY-014 | `EXPIRED`; nueva intención |
| 18 | Cambio de terminal con operación en curso | PAY-012 | Bloqueado hasta resolver |
| 19 | Dos equipos confirman el mismo pago | PAY-010/011 | Un solo efecto (versión o índice) |
| 20 | Instalación y actualización sin pérdida | ARQ-INST | Migraciones probadas sobre copia de la base real |

## 5. Regresión visual

1366×768 y 1920×1080, claro y oscuro, para el diálogo de cobro y el monitor del cliente (PAY-013/015).
Los golden masters no se reemplazan sin un cambio funcional aprobado.

## 6. Cómo correr

```bash
cd pos_spj_v13.4
QT_QPA_PLATFORM=offscreen python -m pytest tests/unit/test_sales_payment_reference.py \
  tests/integration/sales/test_payment_reference_traceability.py \
  tests/integration/finance/test_processor_account_mirror.py \
  tests/integration/cash_register/test_cut_payment_breakdown.py -q -p no:cacheprovider
```
