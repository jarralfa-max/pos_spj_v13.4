"""Bitácora de la transformación directa (migración 343, auditoría 32cfbf).

Un renglón por `operation_id`: guarda la orden que se creó y el UUIDv7 de cada
etapa, generados una sola vez, para que repetir la acción la RETOME en vez de
crear otra orden."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

#: Etapas de la acción única, en orden.
STEPS = ("create", "approve", "prepare", "release", "execute")


@dataclass
class DirectTransformationRecord:
    id: str
    operation_id: str
    branch_id: str
    warehouse_id: str
    input_product_id: str
    lot_id: str
    input_weight: str
    processing_order_id: str | None
    step_operations: dict[str, str]
    status: str
    last_error: str | None
    created_by_user_id: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DirectTransformationRepository:
    _COLUMNS = ("id", "operation_id", "branch_id", "warehouse_id", "input_product_id",
                "lot_id", "input_weight", "processing_order_id", "step_operations_json",
                "status", "last_error", "created_by_user_id")

    def __init__(self, connection) -> None:
        self._conn = connection

    def get_by_operation(self, operation_id: str) -> DirectTransformationRecord | None:
        row = self._conn.execute(
            f"SELECT {', '.join(self._COLUMNS)} FROM direct_transformations"
            " WHERE operation_id=?", (operation_id,)).fetchone()
        if row is None:
            return None
        datos = dict(zip(self._COLUMNS, tuple(row)))
        pasos = json.loads(datos.pop("step_operations_json") or "{}")
        return DirectTransformationRecord(step_operations=pasos, **datos)

    def start(self, *, operation_id: str, branch_id: str, warehouse_id: str,
              input_product_id: str, lot_id: str, input_weight, actor_user_id: str,
              ) -> DirectTransformationRecord:
        registro = DirectTransformationRecord(
            id=new_uuid(), operation_id=operation_id, branch_id=branch_id,
            warehouse_id=warehouse_id, input_product_id=input_product_id, lot_id=lot_id,
            input_weight=str(input_weight), processing_order_id=None,
            step_operations={paso: new_uuid() for paso in STEPS}, status="STARTED",
            last_error=None, created_by_user_id=actor_user_id)
        ahora = _now()
        self._conn.execute(
            "INSERT INTO direct_transformations (id, operation_id, branch_id, warehouse_id,"
            " input_product_id, lot_id, input_weight, processing_order_id,"
            " step_operations_json, status, last_error, created_by_user_id, created_at,"
            " updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (registro.id, operation_id, branch_id, warehouse_id, input_product_id, lot_id,
             registro.input_weight, None, json.dumps(registro.step_operations), "STARTED",
             None, actor_user_id, ahora, ahora))
        return registro

    def update(self, record_id: str, *, processing_order_id: str | None = None,
               status: str | None = None, last_error: str | None = None) -> None:
        campos, valores = ["updated_at=?"], [_now()]
        if processing_order_id is not None:
            campos.append("processing_order_id=?")
            valores.append(processing_order_id)
        if status is not None:
            campos.append("status=?")
            valores.append(status)
            campos.append("last_error=?")
            valores.append(last_error)
        self._conn.execute(f"UPDATE direct_transformations SET {', '.join(campos)} WHERE id=?",
                           (*valores, record_id))
