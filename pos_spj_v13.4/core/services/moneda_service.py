
# core/services/moneda_service.py — SPJ POS v10
"""Conversion de monedas y registro de tasas."""
from __future__ import annotations
import logging
from datetime import date
from core.db.connection import get_connection
logger = logging.getLogger("spj.moneda")

class MonedaService:
    def __init__(self, conn=None):
        self.conn = conn or get_connection(); self._init_tables()
    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS tipos_cambio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                moneda_origen TEXT NOT NULL, moneda_destino TEXT DEFAULT 'MXN',
                tasa DECIMAL(12,6) NOT NULL, fuente TEXT DEFAULT 'manual',
                fecha DATE DEFAULT (date('now')), activa INTEGER DEFAULT 1
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tc_fecha
                ON tipos_cambio(moneda_origen, moneda_destino, fecha);
        """)
        # Seed USD default
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO tipos_cambio(moneda_origen,tasa,fecha) VALUES('USD',17.5,date('now'))")
            self.conn.commit()
        except Exception: pass

    def get_tasa(self, moneda: str = "USD", fecha: str = None) -> float:
        fecha = fecha or date.today().isoformat()
        row = self.conn.execute(
            "SELECT tasa FROM tipos_cambio WHERE moneda_origen=? AND fecha<=? ORDER BY fecha DESC LIMIT 1",
            (moneda, fecha)).fetchone()
        return float(row[0]) if row else 1.0

    def convertir(self, monto: float, moneda_origen: str = "USD",
                  moneda_destino: str = "MXN") -> dict:
        if moneda_origen == moneda_destino:
            return {"original": monto, "convertido": monto, "tasa": 1.0, "moneda": moneda_destino}
        tasa = self.get_tasa(moneda_origen)
        convertido = round(monto * tasa, 2)
        return {"original": monto, "convertido": convertido, "tasa": tasa,
                "moneda_origen": moneda_origen, "moneda_destino": moneda_destino}

    def registrar_tasa(self, moneda: str, tasa: float, fuente: str = "manual") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO tipos_cambio(moneda_origen,tasa,fuente,fecha) VALUES(?,?,?,date('now'))",
            (moneda, tasa, fuente))
        try: self.conn.commit()
        except Exception: pass
        logger.info("Tasa actualizada: 1 %s = %.4f MXN", moneda, tasa)
