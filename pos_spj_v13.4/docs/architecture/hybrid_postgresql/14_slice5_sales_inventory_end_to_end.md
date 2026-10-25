# Slice 5 — Ventas e Inventario de punta a punta (§7 Inventario, §7 Ventas/POS)

Fecha: 2026-10-25. Migración central **p003**.

## Hallazgo que condicionó el slice

`INVENTORY_MOVEMENT_POSTED` **no llevaba cantidades**: sólo el producto del primer renglón y el tipo de
movimiento. Con eso el servidor central no podía reconstruir existencias. Tampoco tenían datos
`INVENTORY_MOVEMENT_REVERSED` ni el documento de origen.

**Decisión:** el evento lleva los **efectos exactos que la estación aplicó a sus saldos**. Cada efecto es
un renglón con:

- producto, lote, almacén, ubicación y estado;
- delta de cantidad y delta de peso, como texto exacto.

`InventoryProjectionService` los registra al aplicarlos y el evento los publica, junto con el documento de
origen.

El servidor central **no vuelve a implementar** las reglas de inventario (`movement_direction`, estados,
reversas, existencia negativa autorizada): sólo suma lo que la estación decidió. Toda escritura de
existencia física pasa por `project_movement` o `project_reversal`; las reservas mueven la cantidad
reservada, no la física.

## Qué se construyó

| Pieza | Archivo |
|---|---|
| Efectos en los eventos de inventario | `inventory_projection_service.py` (`effects`), `movement_posting.py`, `reverse_inventory_movement.py` |
| Payload limpio para eventos «planos» | `infrastructure/sync/replication_sources.py` (no repite los campos del sobre) |
| Proyecciones centrales | `migrations/pg/p003_central_sales_inventory.py` (detalle abajo) |
| Proyector (traductores puros + ciclo) | `backend/application/sync/central_projection.py` |
| SQL de proyección | `backend/infrastructure/central/projection_repository.py` |
| Proyección tras cada ingesta + reproceso | `central_app.py` (`CentralSyncWorkflow._project`), `scripts/central_stations.py project` |

**Proyecciones de `p003`:**

- `central_sales`, con renglones, pagos y devoluciones;
- `central_stock_movements` y `central_stock_effects`;
- la vista `central_stock_on_hand`;
- `central_projection_log`.

### Reglas

| Hecho | Proyección |
|---|---|
| `SALE_COMPLETED` | Venta con totales, renglones (cantidad, importe, costo unitario) y pagos, tal como la cerró la caja |
| `SALE_CANCELLED` / `SALE_REVERSED` | Cambia el estado de la venta, si existe |
| `SALE_RETURNED` | Devolución con su importe |
| `INVENTORY_MOVEMENT_POSTED` / `…_REVERSED` | Movimiento y sus efectos. La existencia central es la suma de los efectos: **conciliable por movimiento** |
| Otros tipos | `SKIPPED`, registrado para no volver a revisarlos |
| Hecho mal formado (un `float`, un movimiento anterior al Slice 5 sin efectos) | `ERROR` con su motivo. No se inventa nada y no traba a los demás |

**Dinero y cantidades** se guardan en `NUMERIC` **sin escala fija**. Una escala fija redondearía en
silencio un valor con más decimales (§5.2). El redondeo lo decide el dominio en la estación.

**Idempotencia:** el registro por hecho y proyector, más `ON CONFLICT DO NOTHING`, hacen que reproyectar
nunca duplique.

**Consistencia:** la proyección corre después de confirmar la ingesta y es de mejor esfuerzo. Los hechos
ya quedaron guardados; si la proyección falla, se reintenta en la siguiente solicitud o con el comando
`project`. Entre sucursales la consistencia es **eventual**; dentro de cada hecho es **fuerte**.

## Evidencia

**Aquí:**

- `tests/unit/central_sync/test_central_projection.py`, 7 pasan.
  - Movimientos del caso de uso **real** (`PostInventoryMovementUseCase`, `ReverseInventoryMovementUseCase`)
    pasan por el mismo lector del motor.
  - La **existencia central cuadra con los saldos locales** de la estación (7.250).
  - La reversa proyecta el inverso exacto.
  - Un movimiento sin efectos no se inventa.
  - La venta conserva totales, cantidades y costos exactos.
  - Un `float` o un valor no numérico se rechazan.
  - El proyector es idempotente y un hecho malo no traba a los demás (libro en memoria, simulación).
- Recorrido local de la caja (SQLite con outbox reales de Ventas e Inventario → motor → API):
  - 3 hechos aceptados;
  - venta con total `137.50`;
  - movimientos con sus efectos.
- Suites de Inventario, Ventas, Caja, Cárnico, Compras y Mermas con los eventos enriquecidos: ver «Resultados».

**En el CI (`central-postgres`, PostgreSQL 16):** `tests/integration/central_pg/test_central_projection_pg.py`
prueba:

1. La caja SQLite manda las ventas y los movimientos por la API real a PostgreSQL y se proyectan.
2. La venta central tiene los totales y costos de la caja.
3. **`central_stock_on_hand` es igual a los saldos locales** (18.750, 2 movimientos).
4. Reproyectar no duplica.

**Resultado en el CI:** _(pendiente del push)_.

## Resultados

Sincronización, ingesta y proyección, más Inventario, Ventas/POS, Caja, Cárnico, Compras y Mermas: **2 188
pasan**. La única falla es la previa `test_losses_schema_born_clean`.

## Pendiente

- **Caja, crédito, fidelidad y finanzas** sobre el libro central: Slice 6.
- **Existencias por lote y fecha de caducidad** en consultas corporativas: los efectos ya traen el lote;
  falta la vista.
- **Ventas canceladas antes de completarse** no existen centralmente. Es correcto: no movieron dinero ni
  inventario.
