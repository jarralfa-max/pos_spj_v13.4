"""Use case for quick customer creation from sales."""

from __future__ import annotations
from backend.shared.ids import new_uuid

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
                customer_id = new_uuid()
                self._db.execute(
                    "INSERT INTO clientes (id, nombre, telefono, email, direccion, puntos, codigo_qr, activo) "
                    "VALUES (?, ?, ?, ?, ?, 0, ?, 1)",
                    (customer_id, command.name.strip(), command.phone, command.email, command.address, command.loyalty_code),
                )
            if command.loyalty_code:
                # Schema canónico (m000): la tarjeta se identifica por codigo_qr
                # (no existe columna `codigo` ni `fecha_emision`). Si la tarjeta
                # ya existe (pregenerada sin dueño) se ASIGNA; si no, se crea
                # con identidad UUIDv7 explícita.
                card = self._db.execute(
                    "SELECT id, COALESCE(id_cliente,'') FROM tarjetas_fidelidad "
                    "WHERE codigo_qr = ? LIMIT 1",
                    (command.loyalty_code,),
                ).fetchone()
                if card is not None:
                    card_id = card["id"] if hasattr(card, "keys") else card[0]
                    self._db.execute(
                        "UPDATE tarjetas_fidelidad SET id_cliente=?, "
                        " estado='asignada', activa=1, "
                        " fecha_asignacion=datetime('now','localtime') "
                        "WHERE id=? AND COALESCE(id_cliente,'')=''",
                        (customer_id, str(card_id)),
                    )
                else:
                    self._db.execute(
                        "INSERT INTO tarjetas_fidelidad "
                        "(id, codigo_qr, id_cliente, estado, activa, nivel, "
                        " fecha_asignacion) "
                        "VALUES (?, ?, ?, 'asignada', 1, 'Bronce', "
                        " datetime('now','localtime'))",
                        (new_uuid(), command.loyalty_code, customer_id),
                    )
            self._db.commit()
        except Exception:
            logger.exception("Unable to create customer operation_id=%s", command.operation_id)
            try:
                self._db.rollback()
            except Exception:
                logger.exception("Rollback failed during customer creation operation_id=%s", command.operation_id)
            raise
        return {"ok": True, "existing": False, "id": str(customer_id), "name": command.name.strip()}

    def find_customer_by_loyalty_code(self, loyalty_code: str) -> dict | None:
        try:
            row = self._db.execute(
                "SELECT c.id, c.nombre FROM clientes c "
                "JOIN tarjetas_fidelidad t ON t.id_cliente = c.id "
                "WHERE t.codigo_qr = ? AND t.activa = 1 LIMIT 1",
                (loyalty_code,),
            ).fetchone()
        except Exception:
            logger.exception("Unable to lookup customer loyalty_code=%s", loyalty_code)
            return None
        if not row:
            return None
        return {
            "id": str(row["id"] if hasattr(row, "keys") else row[0]),
            "name": str(row["nombre"] if hasattr(row, "keys") else row[1]),
        }
