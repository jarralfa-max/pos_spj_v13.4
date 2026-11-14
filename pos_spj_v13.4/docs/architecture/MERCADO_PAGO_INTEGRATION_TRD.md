# Mercado Pago — Documento de requisitos técnicos (TRD)

- **Ítem:** SDLC-PAY-001 · **Fecha:** 2026-11-09
- **Fuentes:**
  - Requisitos: `docs/sdlc/inputs/mercado-pago.md`.
  - Auditoría: `git show 0d8c5844:pos_spj_v13.4/docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`.
  - Decisiones: [`MERCADO_PAGO_INTEGRATION_ADR.md`](MERCADO_PAGO_INTEGRATION_ADR.md).
- **Documentos hermanos:**
  - [APPFLOW](MERCADO_PAGO_INTEGRATION_APPFLOW.md)
  - [DATA_MODEL](MERCADO_PAGO_INTEGRATION_DATA_MODEL.md)
  - [SECURITY](MERCADO_PAGO_INTEGRATION_SECURITY.md)
  - [UX](MERCADO_PAGO_INTEGRATION_UX.md)
  - [TEST_PLAN](MERCADO_PAGO_INTEGRATION_TEST_PLAN.md)
- Este documento **no** autoriza a construir: cada fase pasa por su intent, spec y plan.

## 1. Objetivo

Que un cobro con Mercado Pago (Point Smart, enlace de pago o QR) quede **verificado contra el proveedor**
antes de completar la venta. También tiene que:

- dejar rastro en Caja, Finanzas y el ticket con su referencia;
- conciliarse contra la liquidación;
- reembolsarse con estado.

Nada de esto puede duplicar contextos, tablas ni pantallas existentes.

## 2. Estado de partida (medido)

| Capacidad | Estado al 2026-11-09 | Evidencia |
|---|---|---|
| Cobro MP en POS | Manual: el cajero cobra fuera y declara el pago | `payment_dialog.py` |
| Referencia obligatoria y única (MP, tarjeta, transferencia) | **Hecho** en `fix/lote-4` | PAY-002, migración 384 |
| Referencia en Caja, Finanzas y ticket | **Hecho** en `fix/lote-4` | PAY-003 |
| Venta MP a la cuenta del procesador (1115), no a la 1120 | **Hecho** en `fix/lote-4` | PAY-004, migración 385 |
| Corte X/Z por medio de pago | **Hecho** en `fix/lote-4` | PAY-005 |
| Reembolso electrónico con estado | **Bloqueado**: faltan decisiones contables (§6) | PAY-006 |
| Orders API, Point, Checkout, QR, webhook central, conciliación | Ausente | Auditoría, Fase 1.5 |
| Único cliente MP vivo | `whatsapp_service/` (preferencias y webhook con defectos) | SDLC-WA-001/002/004 |

## 3. Arquitectura objetivo

```
POS / CRM / Pedidos / WhatsApp
   → casos de uso de Pagos (backend/application/payments/)        PAY-007
   → dominio de Pagos: PaymentIntent, estados, reglas              PAY-007/008
   → PaymentProviderPort  (ADR-MP-003)
   → MercadoPagoAdapter (httpx, ADR-MP-004) + ACL de estados       PAY-009
   → API Mercado Pago (Orders API: point / online)
Webhook (ngrok, ADR-MP-002) → inbox durable → worker → consulta remota → efecto idempotente   PAY-010
Tarea de conciliación por consulta (intenciones pendientes o inciertas)                       PAY-011
```

### Qué no es del proveedor

El proveedor no es dueño de:

- la venta, el inventario ni la caja;
- las cuentas ni las reglas de fidelidad;
- los descuentos ni el crédito.

Pagos sólo informa a Ventas que una intención quedó `APPROVED` y verificada. Ventas completa con su
`CheckoutSaleUseCase` de siempre, la única ruta de cierre que vigila
`tests/architecture/test_sales_single_completion_path.py`.

### Dónde corre

ADR-MP-001 y ADR-MP-002 lo deciden mientras tanto:

- el adaptador y el token, en cada caja;
- el receptor de webhooks, en un equipo encendido 24/7 detrás de ngrok.

El diseño no supone servidor central. Cuando exista el servicio local (SDLC-ARQ-HYB-001), el adaptador
se mueve detrás del mismo puerto.

### Qué se reutiliza (auditoría, «Reutilizable»)

| Pieza | Para qué |
|---|---|
| Clasificación de liquidación de Caja (`settlements.py`) | Clasificar el cobro en Caja |
| `TreasuryAccountType.PAYMENT_PROCESSOR` | La cuenta de tesorería del procesador |
| Conciliación bancaria genérica | Conciliar la liquidación (PAY-019) |
| `ReplicationOutboxService` | Patrón de reintentos |
| Inbox de WhatsApp | Patrón persistir → 200 → worker |
| `WorkstationDeviceAssignment` con rol `PAYMENT_TERMINAL` | Vincular terminal y estación |
| `qr_matrix()` | QR dinámico |
| `ScaleMonitor` | Patrón de indicador |
| `CustomerDisplayWindow` | Monitor del cliente |
| `EncryptedLocalSecretStore` / Credential Manager | Almacén del token |
| Permisos `POS.pago.mercado_pago`, `CAJA.terminal_pago.*`, `CAJA.reembolso.*`, `FINANZAS.conciliacion.*` | Permisos de pagos |

## 4. Fases, dependencias, riesgos y criterios de aceptación

| Fase | Ítems | Depende de | Riesgo principal | Criterio de aceptación |
|---|---|---|---|---|
| A. Contención | PAY-002, 003, 004, 005 (hechos) · PAY-006 (bloqueado) | — | Reembolsos «ejecutados» sin hacerse | Referencia única y trazable; corte por medio; reembolso con estado y evidencia |
| B. Diseño | PAY-001 (este) | — | Construir el adaptador en el lugar equivocado | ADR aprobadas por el responsable |
| C. Contratos | PAY-007 → PAY-008; PAY-023; PAY-024 | PAY-001, SDLC-ARQ-IDEM-001 | Venta completada sin pago verificado | `PaymentIntent` con estados; la venta no se completa sin `APPROVED` verificado; los puntos no acumulan sobre pagos pendientes |
| D. Credencial y adaptador | PAY-022, SDLC-SEC-006, PAY-009 | C, ADR-MP-001/004 | Token expuesto; «Configurado» ≠ «Conectado» | Prueba de conexión real; ambiente sandbox/producción; rotación; adaptador probado con `MockTransport` |
| E. Webhook y consulta | PAY-010, PAY-011 | D, SDLC-WA-002 | Webhook perdido o duplicado | Inbox antes de 200; duplicado idempotente; tardío no retrocede; pago sin webhook resuelto por consulta |
| F. Point | PAY-012 → PAY-013 | E, SDLC-ARQ-TERM-001 | Dos estaciones en una terminal; timeout cobra dos veces | Exclusión por terminal; mismo `X-Idempotency-Key` al reintentar; recuperación tras reinicio |
| G. Checkout y QR | PAY-014 → PAY-015 | D, E | Enlaces duplicados entre canales | Un intento por venta o pedido; vigencia; QR en diálogo y monitor |
| H. Mixtos y offline | PAY-016, PAY-017 | C, SDLC-ARQ-HYB-001/002 | Porción electrónica que falla a la mitad | Compensación; Decimal sin float; sin red no se crean órdenes (decisión HYB-002: «Mercado Pago no» sin internet) |
| I. Finanzas | PAY-018 → PAY-019 | PAY-004 | Comisión e IVA sin asiento; depósito duplica ingreso | Bruto, comisión, IVA de comisión y neto; `CAPTURED → SETTLED → RECONCILED` |
| J. Canales | PAY-025 | G, SDLC-WA-003, SDLC-ORD-003 | El microservicio sigue siendo dueño de estado financiero | WhatsApp pide la orden al ERP; no escribe `anticipos` ni `ventas` |
| K. Reembolsos API y contracargos | PAY-020 → PAY-021 | PAY-006, D, E | Reembolso doble | Estados, parciales, eventos tardíos idempotentes |
| L. Cierre | PAY-027, PAY-026, PAY-028, PAY-029 | todas | — | 20 escenarios de fallo en verde (TEST_PLAN §4); BI por pago; runbook |

## 5. Instalador y despliegue (Fase 18)

- Sin dependencias nuevas: `httpx` ya se empaqueta (ADR-MP-004).
- Sin servicio nuevo obligatorio en cada caja. El receptor de webhooks usa el componente opcional
  existente (`installer/windows/spj_setup.iss:111-112,139-142`, `spj.spec:17-24,98-113`) en el equipo
  anfitrión, más ngrok instalado aparte.
- Sin reglas de firewall entrante.
- Migraciones nuevas sólo por los ítems C, I y K, cada una registrada en `migrations/engine.py`.
- **No verificable aquí:** el instalador no se construyó en esta sesión.

## 6. Decisiones pendientes

- **PAY-006, reembolsos.** Tres preguntas al responsable:
  1. ¿En qué cuenta queda un reembolso electrónico **solicitado y aún no confirmado**? Por ejemplo, una
     cuenta nueva de pasivo «Reembolsos por pagar a clientes». ¿O se difiere todo el asiento de la
     devolución hasta confirmar?
  2. En el reverso de una venta MP, el asiento de reversa abona hoy la cuenta del procesador en el acto.
     ¿Pasa por la misma cuenta transitoria hasta confirmar?
  3. Si el reembolso se **rechaza**, ¿qué pasa con la devolución ya registrada? ¿Efectivo, vale, saldo a
     favor o se revierte?
- **ADR-MP-001:** el criterio de salida del token en cada caja; la respuesta contradice el plan maestro.
- **ADR-MP-003 y ADR-MP-004:** necesitan aprobación.
- Siguen abiertas en el backlog las de PAY-008, 012, 017, 018, 019, 021, 022 y 028.
