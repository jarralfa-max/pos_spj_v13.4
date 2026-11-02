# SDLC-PAY-007 — No existe contexto de pagos: sin intención de pago, estados, puerto de proveedor ni capa anticorrupción

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 3 · Fase 20 pasos 7-8 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 1.1/3 «Intención de pago…» (`ausente`) y «PaymentProviderPort + ACL» (`ausente / duplicado`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-001, SDLC-ARQ-IDEM-001

## Problema
El único modelo de pago es el VO inmutable `SalePayment`, sin estado. No existe una intención de pago idempotente con importe congelado, ni un puerto de proveedor con capa anticorrupción que traduzca estados externos a estados internos. Hay seis puertos parciales en distintos contextos y ninguno es canónico; `ChargePaymentTerminalUseCase` es síncrono y sólo se usa en pruebas.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/domain/sales/value_objects/sale_payment.py:26`
- `backend/application/cash_register/hardware.py:61`; `hardware_use_cases.py:135-170`; `backend/infrastructure/integrations/sales_payment_terminal_client.py:37` (sólo pruebas)
- `backend/infrastructure/hardware/cash_register/drivers.py:49` — sin adquirente real
- `whatsapp_service/domain/whatsapp/payment_provider_ports.py:30`
- Feature flags reutilizables: `backend/domain/feature_flags/enums.py:15-31` (sólo consultados en frontend)
- Prueba: `tests/unit/test_sales_hardware.py`, `tests/unit/cash_register/test_cash_hardware_drivers.py` (puerto, no flujo)

## Impacto
Sin esto no hay Point, Checkout, QR, webhooks ni reembolsos verificables.

## Objetivo
- Intención de pago con UUIDv7, importe Decimal congelado, moneda, venta/pedido de origen, clave de idempotencia estable por operación lógica y estados internos (creada, esperando, aprobada, rechazada, cancelada, expirada, desconocida).
- Puerto de proveedor con operaciones crear orden, consultar, cancelar, reembolsar, verificar webhook; un proveedor falso para pruebas.
- Capa anticorrupción: tabla explícita estado externo → interno; un estado tardío nunca retrocede uno confirmado.
- Se reutiliza o retira cada puerto existente según el ADR de PAY-001; activación por feature flag por sucursal verificada en backend.

## Alcance
- **Incluye:** Dominio, aplicación, persistencia (migración), proveedor falso, pruebas unitarias de estados e idempotencia.
- **No incluye:** Adaptador real (PAY-009); integración con la venta (PAY-008).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-ARQ-IDEM-001..005 (idempotencia); SDLC-CORE-002 (formato de operation_id derivados).

## Preguntas abiertas
- Ninguna por ahora.
