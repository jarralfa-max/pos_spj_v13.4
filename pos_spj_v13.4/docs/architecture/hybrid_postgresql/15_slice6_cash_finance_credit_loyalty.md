# Slice 6 — Caja, Finanzas, Crédito y Fidelidad en el servidor central (§6.5, §7)

Fecha: 2026-10-25. Migración central **p004**.

Mismo principio que el Slice 5: el servidor central **proyecta lo que cada estación decidió** y no
recalcula reglas de negocio. Cuando un evento no traía lo necesario, se completó **en la estación**, en un
solo punto común, con lo que el propio dominio ya sabe.

## Hallazgos que se corrigieron

| # | Hallazgo | Corrección |
|---|---|---|
| 1 | `JOURNAL_ENTRY_POSTED/REVERSED` sólo traía totales: ni cuentas, ni cargos, ni abonos | El evento lleva sus renglones (detalle abajo) |
| 2 | Los eventos de puntos traían la cantidad, pero no **a quién** pertenecían; la reversa ni la cantidad | `_emit` de Fidelidad agrega los datos del libro (detalle abajo) |
| 3 | **El renglón por cobrar de una venta a crédito no llevaba al cliente** (cuenta 1130 sin `customer_id`) | `sale_completed_handler` lo llena; los demás orígenes de cuentas por cobrar ya lo hacían (detalle abajo) |

**1. Renglones del asiento.** Cada renglón lleva:

- la cuenta por **código** y **tipo**, además del id, porque los ids son de cada instalación y pueden no
  coincidir entre sucursales;
- cargo y abono en moneda base, rol del renglón y dimensiones;
- la marca `is_receivable`, que sale de los perfiles de contabilización de la estación y no se adivina por
  código.

**2. Datos del libro de puntos.** `_emit` de Fidelidad agrega, para los eventos del libro:

- transacción, cuenta, cliente y membresía;
- tipo, estado y puntos;
- `counts_toward_balance`, tal como lo decide `LoyaltyBalancePolicy`.

**3. Cliente en el renglón por cobrar.** Los otros cuatro orígenes (cuenta por cobrar, cobro, aplicación y
castigo) ya llenaban el cliente.

El tercero es un defecto **local**, no sólo central. Con el cliente vacío en el renglón por cobrar, el
mayor no podía desglosar las cuentas por cobrar por cliente desde los asientos. Los asientos ya
contabilizados en la base real conservan el campo vacío; la corrección rige para los nuevos.

## Proyecciones (p004)

| Contexto | Tablas | Vista de conciliación |
|---|---|---|
| Caja | `central_cash_shifts`, `central_cash_movements` (importe **firmado**), `central_cash_cuts` | — (suma por turno) |
| Finanzas | `central_journal_entries` (`CHECK` debe = haber), `central_journal_lines` | `central_trial_balance` (balanza por sucursal y cuenta), `central_receivables` (saldo por cobrar por cliente) |
| Crédito | `central_credit_accounts` (límite y estado) | `central_credit_exposure`: límite, por cobrar **consolidado de todas las sucursales** y disponible |
| Fidelidad | `central_loyalty_transactions` (una fila por **transacción**) | `central_loyalty_balances` (la misma regla de saldo de la estación) |

**Importe firmado en Caja:** las entradas suman y las salidas restan. Un retiro a caja fuerte sale del
cajón, y la reversa es el inverso del movimiento original.

### Reglas financieras

- **Asiento descuadrado:** el traductor lo rechaza (queda en `ERROR`, visible) y, como segunda barrera, la
  base lo impide con un `CHECK`. Lo mismo pasa si los renglones no suman los totales del asiento.
- **Sin renglones:** un asiento anterior a este slice no se inventa; queda en `ERROR`.
- **Reversa de caja antes que su original:** se rechaza. No ocurre en la práctica, porque la secuencia de
  la estación los ordena.
- **Puntos:** confirmar una reserva actualiza la misma transacción, así que nunca resta dos veces.

**La exposición de crédito consolidada** es la ventaja concreta del servidor central. Cada sucursal ve sólo
lo que se le debe a ella, mientras que la vista central suma las cuentas por cobrar del cliente en
**todas** las sucursales y las compara con su límite.

## Evidencia

**Aquí:** `tests/integration/central_sync/test_slice6_projection.py`, 7 pasan.

- **Finanzas:** una venta a crédito contabilizada por el **manejador real** se proyecta cuadrada, con el
  renglón 1130 marcado como por cobrar y con el cliente. Esta prueba destapó el hallazgo 3.
- **Fidelidad:** gana, reserva y confirma por los **casos de uso reales**. **El saldo central es igual al de
  `LoyaltyBalancePolicy` en la estación (70).**
- **Caja:** importes firmados, reversa inversa, retiro a caja fuerte y corte Z exacto.
- **Crédito:** aprobación, cambio de límite y bloqueo.
- **Rechazos:** un asiento descuadrado o sin renglones no se proyecta.

Además, el recorrido local de una caja SQLite con los cuatro contextos dio **9 hechos enviados y 0
muertos**, y los 9 se traducen sin error.

**En el CI (`central-postgres`, PostgreSQL 16):** `tests/integration/central_pg/test_slice6_projection_pg.py`
recorre caja SQLite → API real → PostgreSQL → proyecciones. Verifica:

- balanza cuadrada (100 = 100);
- por cobrar del cliente: 100;
- exposición: 5 000 − 100 = 4 900;
- puntos: 70;
- caja: +150 − 100 = 50, con el corte de −0.50;
- cero proyecciones en `ERROR`;
- la base misma rechaza un asiento descuadrado.

**Resultado en el CI:** el trabajo `central-postgres` de la ejecución 40222035890 (commit `3219ad86`,
2026-10-25) pasó **en verde** contra PostgreSQL 16.

**Regresión local:** Fidelidad, Finanzas, Caja, Crédito, Ventas, sincronización e ingesta: **1 142 pasan**.

## Pendiente

- **Devoluciones de caja** (`CASH_REFUND_*`): el dinero sale por `CASH_MOVEMENT_RECORDED`, que ya se
  proyecta. El evento de la devolución en sí no se proyecta por separado.
- **Transacciones de puntos PENDING que pasan a disponibles** sin un evento nuevo. Si existiera ese camino,
  el servidor sólo lo vería con el siguiente evento de la transacción. Se documenta como límite.
- **Crédito con límite por cliente desde el servidor** (decisión corporativa) y bloqueo de venta por
  exposición consolidada: requiere bajar datos a la estación (Slice 7, datos maestros).
- **Pantallas corporativas** que lean estas vistas: Slice 9 (BI) y el dashboard web.
