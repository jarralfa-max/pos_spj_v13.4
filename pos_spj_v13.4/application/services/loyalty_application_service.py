from __future__ import annotations

from repositories.loyalty_repository import LoyaltyRepository


class LoyaltyApplicationService:
    def __init__(self, db_conn, loyalty_repository: LoyaltyRepository | None = None):
        self.db = db_conn
        self.repo = loyalty_repository or LoyaltyRepository(db_conn)

    def award_points_for_sale(self, *, cliente_id: int, venta_id: str, puntos: int, sucursal_id: int = 1, usuario: str = ""):
        ok = self.repo.append_ledger_entry(
            cliente_id=cliente_id,
            tipo="acumulacion",
            puntos=max(0, int(puntos)),
            referencia=str(venta_id),
            descripcion=f"Acumulación venta #{venta_id}",
            sucursal_id=sucursal_id,
            usuario=usuario,
        )
        return {"ok": ok, "idempotent": not ok, "saldo": self.repo.get_balance(cliente_id)}

    def preview_redemption(self, *, cliente_id: int, puntos_solicitados: int):
        saldo = self.repo.get_balance(cliente_id)
        canjear = max(0, min(int(puntos_solicitados), saldo))
        return {"saldo": saldo, "puntos_solicitados": int(puntos_solicitados), "puntos_canjeables": canjear}

    def redeem_points_for_sale(self, *, cliente_id: int, venta_id: str, puntos: int, sucursal_id: int = 1, usuario: str = ""):
        req = max(0, int(puntos))
        preview = self.preview_redemption(cliente_id=cliente_id, puntos_solicitados=req)
        canjear = preview["puntos_canjeables"]
        if canjear <= 0:
            return {"ok": False, "error": "SIN_SALDO"}
        ok = self.repo.append_ledger_entry(
            cliente_id=cliente_id,
            tipo="canje",
            puntos=-canjear,
            referencia=str(venta_id),
            descripcion=f"Canje venta #{venta_id}",
            sucursal_id=sucursal_id,
            usuario=usuario,
        )
        return {"ok": ok, "idempotent": not ok, "puntos_canjeados": canjear, "saldo": self.repo.get_balance(cliente_id)}

    def reverse_redemption(self, *, cliente_id: int, venta_id: str, puntos: int, sucursal_id: int = 1, usuario: str = ""):
        ref = f"reversa:{venta_id}"
        ok = self.repo.append_ledger_entry(cliente_id=cliente_id, tipo="reversa", puntos=abs(int(puntos)), referencia=ref,
                                           descripcion=f"Reversa canje venta #{venta_id}", sucursal_id=sucursal_id, usuario=usuario)
        return {"ok": ok, "idempotent": not ok, "saldo": self.repo.get_balance(cliente_id)}

    def expire_points(self, *, cliente_id: int, referencia: str, puntos: int):
        ok = self.repo.append_ledger_entry(cliente_id=cliente_id, tipo="ajuste", puntos=-abs(int(puntos)), referencia=referencia,
                                           descripcion="Expiración automática")
        return {"ok": ok, "idempotent": not ok, "saldo": self.repo.get_balance(cliente_id)}

    def assign_card_to_customer(self, *, cliente_id: int, codigo: str):
        self.repo.assign_card(cliente_id, codigo)
        return {"ok": True, "card": self.repo.get_card_by_code(codigo)}

    def get_customer_loyalty_summary(self, *, cliente_id: int):
        return self.repo.get_customer_summary(cliente_id)
