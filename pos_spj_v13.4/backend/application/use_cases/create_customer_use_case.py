"""Use case for quick customer creation from sales."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging

logger = logging.getLogger("spj.customer.create")


@dataclass(frozen=True)
class CreateCustomerCommand:
    name: str
    phone: str = ""
    email: str = ""
    address: str = ""
    loyalty_code: str | None = None
    operation_id: str = ""


class CreateCustomerUseCase:
    """Creates a customer and optional loyalty card outside the UI layer."""

    def __init__(self, db_conn: Any, customer_repository: Any | None = None) -> None:
        self._db = db_conn
        self._customer_repository = customer_repository

    def execute(self, command: CreateCustomerCommand) -> dict:
        if not command.name.strip():
            raise ValueError("name is required")
        if command.loyalty_code:
            existing = self.find_customer_by_loyalty_code(command.loyalty_code)
            if existing:
                return {"ok": True, "existing": True, **existing}
        try:
            if self._customer_repository is not None:
                customer_id = self._customer_repository.crear(
                    nombre=command.name.strip(),
                    telefono=command.phone,
                    email=command.email,
                    direccion=command.address,
                    codigo_fidelidad=command.loyalty_code,
                )
            else:
                cur = self._db.execute(
                    "INSERT INTO clientes (nombre, telefono, email, direccion, puntos, codigo_qr, activo) "
                    "VALUES (?, ?, ?, ?, 0, ?, 1)",
                    (command.name.strip(), command.phone, command.email, command.address, command.loyalty_code),
                )
                customer_id = cur.lastrowid
            if command.loyalty_code:
                self._db.execute(
                    "INSERT OR IGNORE INTO tarjetas_fidelidad "
                    "(codigo, id_cliente, nivel, activa, fecha_emision) "
                    "VALUES (?, ?, 'Bronce', 1, datetime('now'))",
                    (command.loyalty_code, customer_id),
                )
            self._db.commit()
        except Exception:
            logger.exception("Unable to create customer operation_id=%s", command.operation_id)
            try:
                self._db.rollback()
            except Exception:
                logger.exception("Rollback failed during customer creation operation_id=%s", command.operation_id)
            raise
        return {"ok": True, "existing": False, "id": int(customer_id), "name": command.name.strip()}

    def find_customer_by_loyalty_code(self, loyalty_code: str) -> dict | None:
        try:
            row = self._db.execute(
                "SELECT c.id, c.nombre FROM clientes c "
                "JOIN tarjetas_fidelidad t ON t.id_cliente = c.id "
                "WHERE t.codigo = ? AND t.activa = 1 LIMIT 1",
                (loyalty_code,),
            ).fetchone()
        except Exception:
            logger.exception("Unable to lookup customer loyalty_code=%s", loyalty_code)
            return None
        if not row:
            return None
        return {
            "id": int(row["id"] if hasattr(row, "keys") else row[0]),
            "name": str(row["nombre"] if hasattr(row, "keys") else row[1]),
        }
