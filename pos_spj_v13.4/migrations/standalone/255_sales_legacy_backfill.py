# migrations/standalone/255_sales_legacy_backfill.py
"""Corte de datos de Ventas, paso 1: el histórico legacy entra al agregado canónico.

Contexto medido (ver `tests/architecture/test_sales_persistence_split_ratchet.py`):
hay DOS modelos vivos para una venta. El POS que el usuario usa persiste en
`sales` desde SALES-19..22; la API REST, cotizaciones, pedidos y anticipos
siguen escribiendo `ventas`; y los 49 lectores (BI, forecast, historial de
cliente, planeación de compras) leen `ventas`. Repuntar esos lectores al
agregado canónico es imposible mientras `sales` no contenga el histórico:
verían una tabla casi vacía. Esta migración es lo que desbloquea ese paso.

QUÉ MIGRA, Y QUÉ NO
Sólo las ventas en los dos estados TERMINALES de venta: `completada` y
`cancelada` (96 y 10 apariciones en el código, los únicos con equivalente
directo en `SaleStatus`).

NO migra las filas cuyo `estado` es de PEDIDO/ENTREGA — `pendiente_wa`,
`programado`, `en_preparacion`, `en_ruta`, `entregado`… — porque no son
ventas: son pedidos que el modelo legacy metió en la misma tabla. Su hogar
canónico es el bounded context Orders/Delivery (`delivery_orders`,
`order_addresses`), que ya existe. Mezclarlos aquí reconstruiría dentro de la
arquitectura nueva justo la tabla-dios que se quiere retirar. Se cuentan y se
reportan, no se pierden: la tabla legacy no se toca.

Tampoco migra una fila a la que le falte identidad real (§16/§17): sin
sucursal resoluble o sin usuario resoluble a un `usuarios.id`, se omite y se
cuenta. Inventar `branch_id=""` o meter un nombre de usuario en una columna
`*_user_id` sería exactamente el "inventar contexto" que §17 prohíbe.

FIDELIDAD DEL SNAPSHOT
`sale_lines.product_snapshot` es NOT NULL y debe ser el estado del producto
EN EL MOMENTO de la venta. Se reconstruye desde la propia fila de
`detalles_venta` (`nombre`, `precio_unitario`, `unidad`, `costo_unitario_real`,
`batch_id`), que es dato punto-en-el-tiempo real — NUNCA desde el catálogo
`productos` de hoy, que daría un snapshot falso.

DINERO
Legacy guarda REAL (float); el agregado guarda TEXT decimal. La conversión es
`Decimal(str(round(v, 2)))`, determinista y sin float en el destino (§39).

IDEMPOTENCIA
`sales.operation_id` es UNIQUE. Las filas legacy pueden traerlo nulo o
repetido, así que el backfill acuña uno determinista por venta:
`legacy-backfill:<venta_id>`. Reejecutar la migración no duplica nada: se
salta todo id ya presente en `sales`.

ADITIVA Y REVERSIBLE
No borra ni modifica una sola fila legacy. `ventas` sigue siendo la fuente que
leen los 49 lectores hasta que se repunten uno a uno. Si algo saliera mal, las
filas insertadas son identificables por su `operation_id`.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger("spj.migrations.255")

# Únicos estados legacy con equivalente directo en `SaleStatus`.
_STATUS_MAP = {
    "completada": "COMPLETED",
    "cancelada": "CANCELLED",
}

_BACKFILL_PREFIX = "legacy-backfill:"


def _dec(value) -> str:
    """REAL legacy -> cadena decimal canónica. Nunca deja float en destino."""
    if value is None:
        return "0"
    try:
        return str(Decimal(str(round(float(value), 2))))
    except (InvalidOperation, TypeError, ValueError):
        return "0"


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _user_index(conn) -> dict[str, str]:
    """usuario (nombre) -> usuarios.id. Sin esto no se migra la fila (§16)."""
    if not _table_exists(conn, "usuarios"):
        return {}
    cols = _columns(conn, "usuarios")
    name_col = next((c for c in ("usuario", "username", "nombre") if c in cols), None)
    if not name_col or "id" not in cols:
        return {}
    index: dict[str, str] = {}
    for row in conn.execute(f"SELECT id, {name_col} FROM usuarios"):
        if row[1]:
            index[str(row[1]).strip().lower()] = str(row[0])
    return index


def _branch_ids(conn) -> set[str]:
    if not _table_exists(conn, "sucursales"):
        return set()
    return {str(r[0]) for r in conn.execute("SELECT id FROM sucursales")}


def run(conn) -> None:
    if not (_table_exists(conn, "ventas") and _table_exists(conn, "sales")):
        logger.info("255: falta `ventas` o `sales`; nada que respaldar.")
        return

    venta_cols = _columns(conn, "ventas")
    detalle_cols = _columns(conn, "detalles_venta") if _table_exists(
        conn, "detalles_venta") else set()

    already = {str(r[0]) for r in conn.execute("SELECT id FROM sales")}
    users = _user_index(conn)
    branches = _branch_ids(conn)

    migrated = skipped_state = skipped_identity = 0

    for venta in conn.execute("SELECT * FROM ventas").fetchall():
        row = {k: venta[i] for i, k in enumerate(venta_cols)} if not hasattr(
            venta, "keys") else dict(venta)
        venta_id = str(row.get("id") or "")
        if not venta_id or venta_id in already:
            continue

        status = _STATUS_MAP.get(str(row.get("estado") or "").strip().lower())
        if status is None:
            # Pedido/entrega o borrador: no es una venta. Su sitio es
            # Orders/Delivery, no este agregado.
            skipped_state += 1
            continue

        branch_id = str(row.get("sucursal_id") or "").strip()
        cashier = users.get(str(row.get("usuario") or "").strip().lower(), "")
        if not branch_id or (branches and branch_id not in branches) or not cashier:
            skipped_identity += 1
            continue

        created_at = str(row.get("fecha") or row.get("created_at") or "")
        conn.execute(
            """
            INSERT INTO sales (
                id, branch_id, cashier_user_id, operation_id, status, sale_number,
                cash_session_id, customer_id, channel, currency_code,
                gross_subtotal, discount_total, promotion_total, coupon_total,
                loyalty_total, tax_total, rounding_adjustment, total,
                sale_level_discount, loyalty_redeemed_amount, version,
                created_at, completed_at, cancelled_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'0','0','0','0','0',?,'0','0',1,?,?,?)
            """,
            (
                venta_id, branch_id, cashier, f"{_BACKFILL_PREFIX}{venta_id}",
                status, row.get("folio"), row.get("turno_id"), row.get("cliente_id"),
                str(row.get("canal") or row.get("source_channel") or "POS"), "MXN",
                _dec(row.get("subtotal")), _dec(row.get("descuento")),
                _dec(row.get("total")), created_at,
                created_at if status == "COMPLETED" else None,
                created_at if status == "CANCELLED" else None,
            ),
        )

        if detalle_cols:
            for det in conn.execute(
                    "SELECT * FROM detalles_venta WHERE venta_id=?", (venta_id,)).fetchall():
                line = dict(det) if hasattr(det, "keys") else {
                    k: det[i] for i, k in enumerate(detalle_cols)}
                # Snapshot punto-en-el-tiempo, tomado de la propia línea.
                snapshot = json.dumps({
                    "source": "legacy_backfill",
                    "name": line.get("nombre"),
                    "unit_price": _dec(line.get("precio_unitario")),
                    "unit": line.get("unidad"),
                    "unit_cost": _dec(line.get("costo_unitario_real")),
                    "batch_id": line.get("batch_id"),
                }, ensure_ascii=False)
                conn.execute(
                    """
                    INSERT INTO sale_lines (
                        id, sale_id, product_id, product_snapshot, quantity,
                        quantity_unit, unit_price, discount_total, tax_total,
                        lot_reference, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,'0',?,?,?)
                    """,
                    (
                        str(line.get("id")), venta_id, str(line.get("producto_id") or ""),
                        snapshot, _dec(line.get("cantidad")),
                        str(line.get("unidad") or "pza"), _dec(line.get("precio_unitario")),
                        _dec(line.get("descuento")), line.get("batch_id"),
                        created_at, created_at,
                    ),
                )

        # Pagos: sólo los que EXISTEN en la tabla legacy. El `forma_pago` de la
        # cabecera no es un registro de pago y sintetizarlo sería inventarlo.
        if _table_exists(conn, "payments"):
            for pay in conn.execute(
                    "SELECT id, method, amount, reference, created_at FROM payments "
                    "WHERE venta_id=?", (venta_id,)).fetchall():
                conn.execute(
                    "INSERT INTO sale_payments (id, sale_id, method, amount, reference,"
                    " captured_by_user_id, captured_at) VALUES (?,?,?,?,?,?,?)",
                    (str(pay[0]), venta_id, str(pay[1]), _dec(pay[2]), pay[3],
                     cashier, str(pay[4] or created_at)),
                )

        migrated += 1

    conn.commit()
    logger.info(
        "255: backfill de ventas legacy -> agregado canónico. "
        "Migradas=%d | omitidas por estado de pedido/entrega=%d | "
        "omitidas por identidad no resoluble=%d",
        migrated, skipped_state, skipped_identity,
    )


up = run
