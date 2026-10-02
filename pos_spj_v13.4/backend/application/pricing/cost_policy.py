"""Política de costo multi-sucursal (§32) y el servicio que decide el costo.

Antes el costo era global "en silencio": la proyección sólo escribía la fila de
empresa (``branch_id=''``) y Compras leía ``product_cost`` con su propia regla.

Ahora:

* La proyección mantiene SIEMPRE las dos vistas: el promedio de empresa y el de
  cada sucursal, cada uno con su propia existencia real. Así cambiar de política
  no pierde historia ni exige recalcular.
* La POLÍTICA (``configuraciones.costing.cost_policy``: ``GLOBAL`` por omisión, o
  ``PER_BRANCH``) decide cuál es "el" costo que ven los consumidores.
* ``ProductCostingService`` es el único que decide; las pantallas sólo consultan.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

COST_POLICY_KEY = "costing.cost_policy"


class CostPolicy(str, Enum):
    GLOBAL = "GLOBAL"
    PER_BRANCH = "PER_BRANCH"


COST_POLICY_LABELS = {
    CostPolicy.GLOBAL: "Global (un costo para toda la empresa)",
    CostPolicy.PER_BRANCH: "Por sucursal (cada sucursal con su propio costo)",
}


class CostPolicySettings:
    def __init__(self, connection) -> None:
        self._conn = connection

    def current(self) -> CostPolicy:
        try:
            row = self._conn.execute("SELECT valor FROM configuraciones WHERE clave=?",
                                     (COST_POLICY_KEY,)).fetchone()
        except sqlite3.OperationalError:
            return CostPolicy.GLOBAL
        try:
            return CostPolicy(str(row[0])) if row and row[0] else CostPolicy.GLOBAL
        except ValueError:
            return CostPolicy.GLOBAL

    def store(self, policy: CostPolicy) -> None:
        self._conn.execute(
            "INSERT INTO configuraciones (clave, valor, tipo, grupo, descripcion)"
            " VALUES (?, ?, 'texto', 'costeo', 'Política de costo multi-sucursal')"
            " ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (COST_POLICY_KEY, policy.value))


@dataclass(frozen=True)
class ProductCostView:
    """Todo lo que se sabe del costo de un producto, y cuál manda."""

    policy: CostPolicy
    currency: str
    company_average_cost: Decimal | None
    company_last_purchase_cost: Decimal | None
    branch_average_cost: Decimal | None
    branch_last_purchase_cost: Decimal | None

    @property
    def average_cost(self) -> Decimal | None:
        """El promedio que rige según la política (sucursal sin historia →
        empresa)."""
        return _by_policy(self.policy, self.company_average_cost, self.branch_average_cost)

    @property
    def last_purchase_cost(self) -> Decimal | None:
        return _by_policy(self.policy, self.company_last_purchase_cost,
                          self.branch_last_purchase_cost)


def _by_policy(policy: "CostPolicy", company, branch):
    """La vista que manda según la política; si ésa no tiene dato, la otra
    (nunca "sin costo" habiendo uno)."""
    first, second = (branch, company) if policy is CostPolicy.PER_BRANCH else (company, branch)
    return first if first is not None else second


class ProductCostingService:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._settings = CostPolicySettings(connection)

    def policy(self) -> CostPolicy:
        return self._settings.current()

    def cost_view(self, product_id: str, branch_id: str | None = None) -> ProductCostView:
        company = self._row(product_id, "")
        branch = self._row(product_id, branch_id) if branch_id else None
        currency = (company or branch or {}).get("currency") or "MXN"
        return ProductCostView(
            policy=self.policy(), currency=currency,
            company_average_cost=_d(company, "average_cost"),
            company_last_purchase_cost=_d(company, "last_cost"),
            branch_average_cost=_d(branch, "average_cost"),
            branch_last_purchase_cost=_d(branch, "last_cost"))

    def _row(self, product_id: str, branch_id: str) -> dict | None:
        # `SELECT *` y leer lo que haya: hay tablas `product_cost` reducidas (sin
        # moneda ni último costo) en instalaciones viejas y en pruebas.
        try:
            cursor = self._conn.execute(
                "SELECT * FROM product_cost WHERE product_id=? AND branch_id=?",
                (product_id, branch_id or ""))
            row = cursor.fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        values = dict(zip([c[0] for c in cursor.description], tuple(row)))
        return {"average_cost": values.get("average_cost"),
                "currency": values.get("average_cost_currency"),
                "last_cost": values.get("last_cost")}


def _d(row: dict | None, key: str) -> Decimal | None:
    if not row or row.get(key) in (None, ""):
        return None
    try:
        return Decimal(str(row[key]))
    except ArithmeticError:
        return None
