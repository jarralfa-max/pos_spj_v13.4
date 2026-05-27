from __future__ import annotations

from typing import Any, Dict, Optional


class SaleLoyaltyPolicy:
    """Canonical loyalty policy with idempotency guard by operation_id."""

    def __init__(self, db_conn, loyalty_service=None, event_bus=None):
        self.db = db_conn
        self.loyalty_service = loyalty_service
        self.event_bus = event_bus
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS loyalty_operations ("
                "operation_id TEXT PRIMARY KEY, kind TEXT NOT NULL, cliente_id INTEGER, "
                "venta_id INTEGER, payload TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
        except Exception:
            pass

    def _seen(self, operation_id: str) -> bool:
        if not operation_id:
            return False
        row = self.db.execute("SELECT 1 FROM loyalty_operations WHERE operation_id=? LIMIT 1", (operation_id,)).fetchone()
        return bool(row)

    def _mark(self, operation_id: str, kind: str, cliente_id: Optional[int], venta_id: Optional[int], payload: str = "") -> None:
        if not operation_id:
            return
        self.db.execute(
            "INSERT OR IGNORE INTO loyalty_operations(operation_id, kind, cliente_id, venta_id, payload) VALUES(?,?,?,?,?)",
            (operation_id, kind, cliente_id, venta_id, payload),
        )

    def preview_redemption(self, cliente_id: int, puntos: int, subtotal: float) -> Dict[str, Any]:
        if not self.loyalty_service:
            return {"ok": False, "descuento": 0.0, "error": "loyalty_service no disponible"}
        return self.loyalty_service.preview_redemption(
            cliente_id=cliente_id, puntos_solicitados=int(max(0, puntos)), subtotal=float(subtotal)
        )

    def apply_redemption(self, cliente_id: int, venta_id: int, puntos: int, operation_id: str) -> Dict[str, Any]:
        if self._seen(operation_id):
            return {"ok": True, "idempotent": True}
        if not self.loyalty_service:
            return {"ok": False, "error": "loyalty_service no disponible"}
        res = self.loyalty_service.apply_redemption(
            cliente_id=cliente_id, venta_id=venta_id, cajero_id="system", subtotal=0.0, puntos=int(max(0, puntos))
        )
        if res.get("ok"):
            self._mark(operation_id, "redeem", cliente_id, venta_id, str(res))
        return res

    def earn_points(self, cliente_id: int, venta_id: int, total: float, operation_id: str, branch_id: int = 0, usuario: str = "") -> Dict[str, Any]:
        if self._seen(operation_id):
            return {"ok": True, "idempotent": True, "puntos_ganados": 0}
        if not self.loyalty_service:
            return {"ok": False, "error": "loyalty_service no disponible"}
        res = self.loyalty_service.process_loyalty_for_sale(
            client_id=cliente_id, total_sale=float(total), branch_id=branch_id, venta_id=venta_id, usuario=str(usuario or "system")
        ) or {}
        self._mark(operation_id, "earn", cliente_id, venta_id, str(res))
        return {"ok": True, **res}

    def reverse_points(self, cliente_id: int, venta_id: int, operation_id: str, puntos: int = 0, usuario: str = "system") -> Dict[str, Any]:
        if self._seen(operation_id):
            return {"ok": True, "idempotent": True}
        # fallback SQL canonicalized here while no loyalty reverse API exists
        self.db.execute("UPDATE clientes SET puntos = MAX(0, COALESCE(puntos,0) - ?) WHERE id = ?", (int(max(0, puntos)), cliente_id))
        self.db.execute(
            "INSERT INTO historico_puntos (cliente_id, tipo, puntos, descripcion, saldo_actual, usuario, venta_id) "
            "SELECT ?, 'CANCELACION', ?, ?, MAX(0, COALESCE(puntos,0) - ?), ?, ? FROM clientes WHERE id=?",
            (cliente_id, -int(max(0, puntos)), f"Reversa venta #{venta_id}", int(max(0, puntos)), usuario, venta_id, cliente_id),
        )
        self._mark(operation_id, "reverse", cliente_id, venta_id, str(puntos))
        return {"ok": True}
