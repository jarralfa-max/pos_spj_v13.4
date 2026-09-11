"""Saldo de puntos de un cliente, sumando los DOS libros que conviven.

    loyalty_transactions   canónico, con muchos escritores vivos
    loyalty_ledger         legacy, ya SIN escritores pero con saldo real

Ninguna migración traslada el segundo al primero: la 225 crea el contexto
acotado y sólo menciona `loyalty_ledger` en su docstring. Así que los puntos
que un cliente acumuló antes de la reconstrucción sólo existen ahí.

Leer únicamente el canónico dejaría a esos clientes con saldo cero. No daría
ningún error: simplemente no podrían canjear nada, y en caja parecería que
nunca acumularon. Es el mismo problema que la exposición de crédito tenía con
`cuentas_por_cobrar`, y se resuelve igual.

NO HAY DOBLE CONTEO: son tablas distintas y ninguna operación se apunta en las
dos — el libro legacy dejó de recibir escrituras antes de que el canónico
empezara. Si algún día se migran esas filas, hay que dejar de sumarlas aquí en
el mismo cambio, o todo cliente migrado duplicaría su saldo.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.loyalty.policies.balance_policy import LoyaltyBalancePolicy
from backend.infrastructure.db.repositories.loyalty.base import LoyaltyRepositoryBase


class LoyaltyPointsBalanceRepository(LoyaltyRepositoryBase):
    def balance_for_customer(self, customer_id: str) -> int:
        """Puntos disponibles, en entero.

        Los puntos son unidades enteras: el cliente tiene 150 puntos, no
        150.4. Se trunca hacia abajo para no regalar un punto que no existe.
        """
        total = self._canonical_balance(customer_id) + self._legacy_balance(customer_id)
        return max(0, int(total))

    def _canonical_balance(self, customer_id: str) -> Decimal:
        """Saldo del libro canónico, derivado del ledger (nunca de un campo).

        Sin cuenta de fidelidad el saldo es cero: un cliente que nunca se
        inscribió no tiene puntos, y eso no es un error que deba propagarse.
        """
        if not self._table_exists("loyalty_accounts"):
            return Decimal("0")
        row = self._query_one(
            "SELECT id FROM loyalty_accounts WHERE customer_id=?", (customer_id,))
        if row is None:
            return Decimal("0")

        from backend.infrastructure.db.repositories.loyalty.transaction_repository import (
            LoyaltyTransactionRepository,
        )

        transacciones = LoyaltyTransactionRepository(self._conn).list_for_account(row["id"])
        return LoyaltyBalancePolicy.balance(transacciones)

    def _legacy_balance(self, customer_id: str) -> Decimal:
        """Saldo histórico en `loyalty_ledger`.

        OJO CON LA IDENTIDAD: ese libro guarda el id LEGACY del cliente
        (`clientes.id`), no el de Customer Master. Consultarlo con
        `customers.id` no da error — devuelve cero, que es indistinguible de
        "este cliente no tiene puntos". El enlace es
        `customers.legacy_customer_id`.

        La resolución es una LECTURA, no `EnsureLegacyCustomerBridgeUseCase`:
        ése crea la fila `clientes` que falte, y consultar un saldo no puede
        dar de alta a nadie. Sin enlace, no hay puntos históricos que sumar.

        Se SUMAN los movimientos en vez de leer `saldo_post`. Esa columna es
        una foto del saldo tras cada apunte: si alguna fila se insertó fuera de
        orden o se corrigió a mano, la última foto miente mientras que la suma
        sigue siendo la verdad del libro.

        Los canjes y reversas ya vienen con signo en `puntos`, así que sumar
        basta; tratarlos por tipo sería reimplementar el signo que el dato ya
        trae.
        """
        if not self._table_exists("loyalty_ledger"):
            return Decimal("0")
        legacy_id = self._legacy_customer_id(customer_id)
        if not legacy_id:
            return Decimal("0")
        row = self._query_one(
            "SELECT COALESCE(SUM(puntos), 0) AS total FROM loyalty_ledger WHERE cliente_id=?",
            (legacy_id,))
        return Decimal(str(row["total"] or 0)) if row else Decimal("0")

    def _legacy_customer_id(self, customer_id: str) -> str:
        """`customers.legacy_customer_id`, o vacío si el cliente nació nativo
        en Customer Master y nunca tuvo registro legacy."""
        if not self._table_exists("customers"):
            return ""
        try:
            row = self._query_one(
                "SELECT legacy_customer_id FROM customers WHERE id=?", (customer_id,))
        except Exception:
            return ""
        return str(row["legacy_customer_id"] or "") if row else ""

    def _table_exists(self, name: str) -> bool:
        return bool(self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
            (name,)).fetchone())
