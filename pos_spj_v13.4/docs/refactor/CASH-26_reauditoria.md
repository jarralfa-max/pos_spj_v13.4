# CASH-26 — Re-auditoría de Caja sobre la base real (bloque 1)

Fecha: 2026-10-07. Disparador: re-pegado del prompt maestro de Caja. CASH-0..25 ya
existían (ver `cash_register_refactor_execution_plan.md` y `CASH-*.md`); esto NO es
una reconstrucción sino una re-auditoría con la app viva.

## Método

1. Copia de `data/spj_pos_database.db` → `run_database_bootstrap_sequence` (la misma
   conexión que `frontend/desktop/app.py` entrega a la shell).
2. Se abrió Caja por la ruta REAL de la shell (`CashRegisterModuleActivator`) y se
   capturó cada una de las 18 rutas a 1366×768.
3. Se recorrió un turno completo por el presentador real con los dos usuarios reales
   (JoseR y Juanis).

Línea base de pruebas: **306 verdes, 1 roja, 5 sin poder recolectarse** — y aun así
la Caja viva no podía cerrar un turno.

> Trampa del arnés: `backend.infrastructure.db.connection.get_connection()` abre en
> AUTOCOMMIT (`isolation_level=None`); con ella el `CashRegisterUnitOfWork` no revierte
> y aparecen falsos "Corte Z a medias". La app usa la conexión del bootstrap, donde el
> rollback sí funciona. Medido y descartado.

## Hallazgos (medidos en la base real)

| # | Severidad | Hallazgo | Estado |
|---|-----------|----------|--------|
| 1 | P0 | Ningún rol tenía las 93 acciones granulares de Caja; sólo dueño/admin operaban por bypass. Un **cajero no podía abrir turno** y, como el POS exige turno, **no podía vender**. La matriz de roles sólo existía dentro de un test, con roles inventados. | Cerrado — migr. 306 |
| 2 | P0 | `cash_denominations` vacía → el conteo ciego no se podía confirmar → **no había Corte Z → el turno nunca cerraba** (el turno real estaba abierto desde el 2026-09-25). | Cerrado — migr. 307 |
| 3 | P0 | Sin límites para fondo/movimiento/bóveda el tope valía $0: **todo ingreso, retiro y retiro a bóveda se rechazaba**. | Cerrado — migr. 307 |
| 4 | P0 | `cash_movement_reasons` y `cash_difference_policies` **no tenían escritor**: retiro a bóveda imposible y Corte Z imposible con cualquier faltante/sobrante. | Cerrado — escritores + migr. 307 |
| 5 | P0 | Folio del Corte X = `X-` + 8 hex del UUIDv7 (marca de tiempo): **el segundo Corte X del minuto reventaba** con `UNIQUE constraint failed`. | Cerrado — folio `X-<suc>-000001` |
| 6 | P0 | Autorización en caliente **muerta**: el diálogo pedía usuario y clave, descartaba la clave y el verificador de sesión rechazaba a cualquier otro usuario. | Cerrado — `VerifyAuthorizerCredentialsUseCase` |
| 7 | P1 | Resolver una diferencia exigía 3 personas; con 2 usuarios reales nunca se resolvía. | Cerrado — regla de 2 personas (migr. 308) |
| 8 | P1 | Configuración = diálogo de texto libre «nombre / valor» (había que teclear `MANUAL_MOVEMENT` y `1000 / 5000`). | Cerrado — altas tipadas + baja |
| 9 | P1 | Límites leídos al abrir Caja: uno nuevo no aplicaba hasta reabrir. | Cerrado — `EffectiveCashLimitPolicy` |
| 10 | P1 | §14: ingreso/retiro con concepto libre — «pago a proveedor» se aceptaba como retiro. | Cerrado — motivo de catálogo obligatorio |
| 11 | P1 | La alerta de diferencia del Corte Z nunca se preparaba (otra `operation_id`). | Cerrado |
| 12 | P1 | Reabrir Caja a mitad del arqueo perdía el conteo abierto (sólo vivía en memoria). | Cerrado |
| 13 | P2 | Capa legacy «FASE 7.7» (`CashRegisterApplicationService`, commands, query service, 3 use cases, `cash_count_service`) sobre el `FinanceService` borrado: cero consumidores; 5 tests no recolectables. | Eliminada |
| 14 | P2 | Pestañas de configuración decorativas: Jerarquía/Vigencias (nadie lee `cash_settings`), Permisos (sin lector), Medios de pago (la clasificación vive en `settlements.py`). | Retiradas |

## Decisiones del usuario (2026-10-07)

* Límites «moderados»: fondo ≤ $2,000 sin autorización (tope $5,000); ingreso/retiro
  manual autoriza arriba de $1,000 (tope $5,000); bóveda autoriza arriba de $10,000
  (tope $50,000).
* Tolerancia $10, crítica desde $200, reincidencia 3 en 30 días; avisos en sistema y WhatsApp.
* Diferencias con **2 personas**: el cajero explica; otra persona revisa **y** resuelve.
  El cajero nunca resuelve la suya (§46).
* Cajero «opera su turno»: abrir, movimientos dentro de límite, bóveda, conteo ciego,
  Corte X y Z, explicar su diferencia, entregar valores, cajón con venta, imprimir.
  No revisa/resuelve, no reversa, no configura, no ve el esperado antes de contar.

## Migraciones

| # | Qué hace |
|---|----------|
| 306 | Acciones de Caja por rol (foto fija contrastada con `ALL_CASH_PERMISSIONS`); borra `crear/editar/eliminar` gruesos. |
| 307 | Denominaciones MXN, motivos §14/§15, límites y tolerancia. Sólo siembra lo que no tenga fila vigente. |
| 308 | Reconstruye `cash_differences` con la regla de 2 personas (la 175 ya nace corregida). |

## Verificación

* Copia de la base real: el turno abierto desde el 2026-09-25 se cerró de punta a punta
  (ingreso, «pago a proveedor» rechazado, bóveda, entrega que recibe Juanis, Cortes
  `X-COR-000001`/`X-COR-000002`, conteo, `Z-COR-000001`, turno CLOSED).
* `tests/e2e/test_cash26_shift_e2e.py`: turno completo con cajero + dueña reales,
  autorización con clave (una clave mala no autoriza), diferencia de $50 explicada por
  el cajero y revisada/resuelta por la dueña; reapertura a mitad del conteo.
* `tests/integration/cash_register/test_cash26_reaudit.py`: 306/307/308, folios,
  límites vigentes, escritores tipados, baja, §14.

## Bloque 2 (2026-10-07): Caja conectada al resto del ERP

| # | Severidad | Hallazgo | Estado |
|---|-----------|----------|--------|
| 15 | P0 | **Finanzas no recibía nada de Caja**: `cash_outbox` sin despachador y `CashFinanceEventRouter` sin suscriptor (§37). | Cerrado — `finance_wiring.py` |
| 16 | P0 | El asiento del corte acreditaba la caja registradora por todo el esperado (fondo y custodia incluidos), aunque esa cuenta sólo recibe lo que asienta Ventas: residuo en cada turno. | Cerrado — acredita `sales_cash` |
| 17 | P0 | **Los cortes nunca se imprimían**: cola HTML para la impresora literal `default-cash-printer`, sin despachador; la pantalla decía «enviado a impresión». | Cerrado — Document Output + ESC/POS (migr. 309) |
| 18 | P1 | Cajón: `StubCashHardwareGateway` en la composición; el POS no abría el cajón al cobrar. | Cerrado — pulso ESC p por la impresora del ticket |
| 19 | P1 | Avisos a oscuras: sin destinatarios ni escritor, envío sólo manual, cuerpo en JSON crudo con UUIDs, WhatsApp nunca inyectado (§39/§40). | Cerrado — migr. 310 + Configuración → Avisos/Destinatarios |
| 20 | P1 | `business_date` siempre NULL; el asiento del Z se fechaba con el día UTC (un Z después de las 18:00 caía al día siguiente). | Cerrado — migr. 311 |
| 21 | P2 | Reembolsos pedía UUIDs a mano (y el nombre del autorizador donde la tabla exige su id). | Cerrado — la página lista; la devolución del POS ejecuta |
| 22 | P2 | Medios de pago leía `cash_payment_methods`, vacía y sin lector. | Cerrado — clasificación de `settlements.py` |

**Decisión tomada por omisión (revisable):** fondo, ingresos, retiros y retiros a bóveda
son custodia entre la caja y el efectivo general; no se asientan uno por uno. El único
efecto contable de un turno es el efectivo de ventas que sale de la caja registradora y la
diferencia. Coherente con los manejadores de Tesorería existentes («Custody events are
acknowledged without creating a second economic effect»).

**Verificado en copia de la base real:** el turno abierto el 24 a las 20:36 (hora local)
cerró con `X-COR-000001` y `Z-COR-000001` impresos en ESC/POS hacia PRN-01 (transporte
interceptado), el cajón recibió el pulso, los 13 eventos de Caja se despacharon, el
sobrante de $50 se asentó (Caja general / Sobrantes de caja) con fecha 2026-09-24, y
JoseR y Juanis recibieron «Sobrante de $50.00 en el corte Z-COR-000001. Cajero: Jose
Rodriguez.»

Pruebas nuevas: `test_cash_finance_dispatch.py` (6), `test_cash_cut_printing.py` (6),
`test_cash_drawer_hardware.py` (4), `test_cash_alerts_delivery.py` (5).

## Pendiente

* Destinatarios de WhatsApp: no hay teléfonos capturados; se agregan en Caja →
  Configuración → Destinatarios. El envío depende de que Integraciones → WhatsApp tenga
  `wa_internal_api_key` y el microservicio arriba; si no, el aviso queda en reintento y
  luego en `DEAD_LETTER` (visible en Notificaciones).
* Mermas usa el mismo patrón (`whatsapp_message_service` que nadie inyecta): sus avisos
  por WhatsApp tampoco salen.
* RRHH: `CashShiftOpened/ClosedAttendanceHandler` siguen sin suscriptor (fuera de Caja).
* Sin folio propio de turno (se muestra `TUR-xxxx` derivado del id).
