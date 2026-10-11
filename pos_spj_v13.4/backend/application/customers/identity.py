"""CustomerIdentityResolver — todas las identidades de un cliente (auditoría CRM
F02/F06/F12/F19, 2026-10-09).

Un cliente puede aparecer en los datos con varios ids:

* su id canónico (``customers.id``);
* su id histórico (``customers.legacy_customer_id``), con el que siguen
  guardadas la deuda de ``cuentas_por_cobrar`` y las ventas legacy;
* los ids de los clientes que se FUSIONARON en él (``customer_merge_records``
  ejecutados) — y, a su vez, los históricos de ésos.

Antes cada lector resolvía (o no) una parte: la exposición de crédito buscaba
la deuda histórica con el id canónico (F02), el historial buscaba ventas
canónicas con el histórico (F12) y nada seguía una fusión (F06). Un solo lugar,
consultas parametrizadas, sólo lectura.
"""

from __future__ import annotations


def _table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
                        (name,)).fetchone() is not None


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


class CustomerIdentityResolver:
    def __init__(self, connection) -> None:
        self._conn = connection

    def canonical_ids(self, customer_id: str) -> tuple[str, ...]:
        """El cliente y los fusionados en él (sin históricos)."""
        ids = [customer_id]
        if _table(self._conn, "customer_merge_records"):
            pending = [customer_id]
            while pending:
                current = pending.pop()
                for (merged,) in self._conn.execute(
                        "SELECT merged_customer_id FROM customer_merge_records"
                        " WHERE master_customer_id=? AND status='EXECUTED'", (current,)):
                    if merged and merged not in ids:
                        ids.append(merged)
                        pending.append(merged)
        return tuple(ids)

    def all_ids(self, customer_id: str) -> tuple[str, ...]:
        """Canónicos + sus ids históricos, sin repetir."""
        ids = list(self.canonical_ids(customer_id))
        if _table(self._conn, "customers") and "legacy_customer_id" in _columns(
                self._conn, "customers"):
            marks = ",".join("?" for _ in ids)
            for (legacy,) in self._conn.execute(
                    f"SELECT legacy_customer_id FROM customers WHERE id IN ({marks})",
                    tuple(ids)).fetchall():
                if legacy and legacy not in ids:
                    ids.append(legacy)
        return tuple(ids)
