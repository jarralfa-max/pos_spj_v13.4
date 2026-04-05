# config/schedules.py — Horarios de sucursales
"""
Consulta horarios de operación por sucursal desde la BD del ERP.
"""
from __future__ import annotations
from datetime import datetime, time
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger("wa.schedules")

# Mapeo día Python (0=lunes) a nombre
_DIAS = {0: "lunes", 1: "martes", 2: "miercoles", 3: "jueves",
         4: "viernes", 5: "sabado", 6: "domingo"}


class ScheduleService:

    def __init__(self, db_conn):
        self.db = db_conn
        self._ensure_table()

    def _ensure_table(self):
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS wa_horarios_sucursal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sucursal_id INTEGER NOT NULL,
                    dia TEXT NOT NULL,
                    hora_apertura TEXT DEFAULT '08:00',
                    hora_cierre TEXT DEFAULT '20:00',
                    activo INTEGER DEFAULT 1,
                    UNIQUE(sucursal_id, dia)
                )
            """)
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("_ensure_table: %s", e)

    def esta_abierta(self, sucursal_id: int,
                     cuando: Optional[datetime] = None) -> bool:
        """Retorna True si la sucursal está abierta en el momento dado."""
        cuando = cuando or datetime.now()
        dia = _DIAS.get(cuando.weekday(), "lunes")
        try:
            row = self.db.execute(
                "SELECT hora_apertura, hora_cierre FROM wa_horarios_sucursal "
                "WHERE sucursal_id=? AND dia=? AND activo=1",
                (sucursal_id, dia)
            ).fetchone()
            if not row:
                return True  # Sin horario configurado = siempre abierta
            apertura = time.fromisoformat(row[0])
            cierre = time.fromisoformat(row[1])
            ahora = cuando.time()
            return apertura <= ahora <= cierre
        except Exception:
            return True  # Fail-open

    def get_horario_hoy(self, sucursal_id: int) -> Optional[Tuple[str, str]]:
        """Retorna (hora_apertura, hora_cierre) de hoy."""
        dia = _DIAS.get(datetime.now().weekday(), "lunes")
        try:
            row = self.db.execute(
                "SELECT hora_apertura, hora_cierre FROM wa_horarios_sucursal "
                "WHERE sucursal_id=? AND dia=? AND activo=1",
                (sucursal_id, dia)
            ).fetchone()
            return (row[0], row[1]) if row else None
        except Exception:
            return None

    def proximo_horario_apertura(self, sucursal_id: int) -> Optional[str]:
        """Retorna texto legible del próximo horario de apertura."""
        from datetime import timedelta
        ahora = datetime.now()
        for delta in range(1, 8):
            futuro = ahora + timedelta(days=delta)
            dia = _DIAS.get(futuro.weekday(), "lunes")
            try:
                row = self.db.execute(
                    "SELECT hora_apertura FROM wa_horarios_sucursal "
                    "WHERE sucursal_id=? AND dia=? AND activo=1",
                    (sucursal_id, dia)
                ).fetchone()
                if row:
                    dia_nombre = dia.capitalize()
                    return f"{dia_nombre} a las {row[0]}"
            except Exception:
                continue
        return "mañana"
