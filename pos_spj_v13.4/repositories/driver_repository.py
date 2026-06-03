from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spj.repositories.driver")


class DriverRepository:
    """Data access for drivers, locations and driver cash cuts.

    The schema keeps legacy Spanish column names for compatibility while exposing
    English-named methods to backend services.
    """

    def __init__(self, db):
        self.db = db
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS drivers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                vehiculo TEXT,
                activo INTEGER DEFAULT 1,
                en_ruta INTEGER DEFAULT 0,
                sucursal_id INTEGER DEFAULT 1,
                usuario_id INTEGER
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS driver_locations (
                driver_id INTEGER,
                chofer_id INTEGER,
                lat REAL,
                lng REAL,
                timestamp DATETIME DEFAULT (datetime('now')),
                actualizado DATETIME
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_driver_cuts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id INTEGER NOT NULL,
                driver_nombre TEXT,
                turno_inicio DATETIME,
                turno_fin DATETIME DEFAULT (datetime('now')),
                entregas_total INTEGER DEFAULT 0,
                efectivo_cobrado REAL DEFAULT 0,
                tarjeta_cobrado REAL DEFAULT 0,
                transfer_cobrado REAL DEFAULT 0,
                total_cobrado REAL DEFAULT 0,
                efectivo_entregado REAL DEFAULT 0,
                diferencia REAL DEFAULT 0,
                usuario_corte TEXT,
                sucursal_id INTEGER DEFAULT 1,
                notas TEXT,
                fecha DATETIME DEFAULT (datetime('now'))
            )
            """
        )
        for table, cols in {
            "drivers": (
                "telefono TEXT", "vehiculo TEXT", "activo INTEGER DEFAULT 1",
                "en_ruta INTEGER DEFAULT 0", "sucursal_id INTEGER DEFAULT 1", "usuario_id INTEGER",
                "personal_id INTEGER", "source_module TEXT DEFAULT 'delivery'",
            ),
            "driver_locations": (
                "driver_id INTEGER", "chofer_id INTEGER", "lat REAL", "lng REAL",
                "timestamp DATETIME", "actualizado DATETIME",
            ),
            "delivery_driver_cuts": (
                "driver_nombre TEXT", "turno_inicio DATETIME", "turno_fin DATETIME",
                "entregas_total INTEGER DEFAULT 0", "efectivo_cobrado REAL DEFAULT 0",
                "tarjeta_cobrado REAL DEFAULT 0", "transfer_cobrado REAL DEFAULT 0",
                "total_cobrado REAL DEFAULT 0", "efectivo_entregado REAL DEFAULT 0",
                "diferencia REAL DEFAULT 0", "usuario_corte TEXT", "sucursal_id INTEGER DEFAULT 1",
                "notas TEXT", "fecha DATETIME",
            ),
        }.items():
            for col in cols:
                try:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
                except Exception:
                    pass
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_drivers_branch_active ON drivers(sucursal_id, activo)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_driver_locations_driver ON driver_locations(driver_id, chofer_id)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_driver_cuts_driver_fecha ON delivery_driver_cuts(driver_id, fecha)")
        try:
            self.db.commit()
        except Exception:
            pass


    def list_drivers(self) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT id, nombre, COALESCE(telefono,'') AS telefono,
                   COALESCE(vehiculo,'') AS vehiculo,
                   COALESCE(activo,1) AS activo,
                   COALESCE(en_ruta,0) AS en_ruta,
                   COALESCE(sucursal_id,1) AS sucursal_id,
                   usuario_id, personal_id, COALESCE(source_module,'delivery') AS source_module
            FROM drivers
            ORDER BY nombre
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def create_driver(self, data: Dict[str, Any]) -> int:
        cur = self.db.execute(
            """
            INSERT INTO drivers(nombre, telefono, vehiculo, activo, sucursal_id, usuario_id)
            VALUES(?,?,?,?,?,?)
            """,
            (
                data.get("nombre"), data.get("telefono", ""), data.get("vehiculo", ""),
                int(data.get("activo", 1)), int(data.get("sucursal_id", 1) or 1),
                data.get("usuario_id"),
            ),
        )
        try:
            self.db.commit()
        except Exception:
            pass
        return int(cur.lastrowid or 0)

    def update_driver(self, driver_id: int, data: Dict[str, Any]) -> None:
        self.db.execute(
            """
            UPDATE drivers
               SET nombre=?, telefono=?, vehiculo=?, activo=?, sucursal_id=?, usuario_id=?
             WHERE id=?
            """,
            (
                data.get("nombre"), data.get("telefono", ""), data.get("vehiculo", ""),
                int(data.get("activo", 1)), int(data.get("sucursal_id", 1) or 1),
                data.get("usuario_id"), driver_id,
            ),
        )
        try:
            self.db.commit()
        except Exception:
            pass

    def deactivate_driver(self, driver_id: int) -> None:
        self.db.execute("UPDATE drivers SET activo=0 WHERE id=?", (driver_id,))
        try:
            self.db.commit()
        except Exception:
            pass

    def list_active_drivers(self, branch_id: int) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT id, nombre, COALESCE(telefono,'') AS telefono,
                   COALESCE(vehiculo,'') AS vehiculo,
                   COALESCE(activo,1) AS activo,
                   COALESCE(en_ruta,0) AS en_ruta,
                   COALESCE(sucursal_id,1) AS sucursal_id,
                   usuario_id
            FROM drivers
            WHERE COALESCE(activo,1)=1
              AND (COALESCE(sucursal_id,1)=? OR COALESCE(sucursal_id,1)=0)
            ORDER BY nombre
            """,
            (branch_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_driver(self, driver_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute("SELECT * FROM drivers WHERE id=?", (driver_id,)).fetchone()
        return dict(row) if row else None

    def assign_driver(self, order_id: int, driver_id: int, usuario: str = "sistema", notes: str = "") -> None:
        driver = self.get_driver(driver_id)
        if not driver:
            raise ValueError("Repartidor no encontrado")
        self.db.execute(
            """
            UPDATE delivery_orders
            SET driver_id=?, responsable_entrega=?, fecha_asignacion=datetime('now'),
                fecha_actualizacion=datetime('now')
            WHERE id=?
            """,
            (driver_id, driver.get("nombre") or "", order_id),
        )
        try:
            self.db.execute(
                """
                INSERT INTO delivery_order_history(order_id, estado_anterior, estado_nuevo, usuario, observacion)
                SELECT id, estado, estado, ?, ? FROM delivery_orders WHERE id=?
                """,
                (usuario, notes or f"Repartidor asignado: {driver.get('nombre') or driver_id}", order_id),
            )
        except Exception:
            pass
        self.db.commit()

    def mark_driver_on_route(self, driver_id: int, value: bool) -> None:
        self.db.execute("UPDATE drivers SET en_ruta=? WHERE id=?", (1 if value else 0, driver_id))
        self.db.commit()

    def get_driver_location(self, driver_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            """
            SELECT COALESCE(driver_id, chofer_id) AS driver_id, lat, lng,
                   COALESCE(actualizado, timestamp) AS timestamp
            FROM driver_locations
            WHERE COALESCE(driver_id, chofer_id)=?
            ORDER BY datetime(COALESCE(actualizado, timestamp)) DESC
            LIMIT 1
            """,
            (driver_id,),
        ).fetchone()
        return dict(row) if row else None

    def save_driver_location(self, driver_id: int, lat: float, lng: float) -> None:
        self.db.execute(
            """
            INSERT INTO driver_locations(driver_id, chofer_id, lat, lng, timestamp, actualizado)
            VALUES(?,?,?,?,datetime('now'),datetime('now'))
            """,
            (driver_id, driver_id, lat, lng),
        )
        self.db.commit()

    def get_driver_cut_summary(self, driver_id: int, branch_id: int, date_from: str = "", date_to: str = "") -> Dict[str, Any]:
        where = ["driver_id=?", "COALESCE(sucursal_id,1)=?", "estado='entregado'"]
        params: List[Any] = [driver_id, branch_id]
        if date_from:
            where.append("date(COALESCE(fecha_entrega, fecha_actualizacion, fecha)) >= date(?)")
            params.append(date_from)
        if date_to:
            where.append("date(COALESCE(fecha_entrega, fecha_actualizacion, fecha)) <= date(?)")
            params.append(date_to)
        rows = self.db.execute(
            f"""
            SELECT id, folio, COALESCE(total,0) AS total,
                   lower(COALESCE(pago_metodo,'')) AS pago_metodo,
                   COALESCE(pago_monto,total,0) AS pago_monto
            FROM delivery_orders
            WHERE {' AND '.join(where)}
            """,
            tuple(params),
        ).fetchall()
        summary = {
            "driver_id": driver_id,
            "branch_id": branch_id,
            "deliveries_total": len(rows),
            "cash_collected": 0.0,
            "card_collected": 0.0,
            "transfer_collected": 0.0,
            "total_collected": 0.0,
            "orders": [dict(r) for r in rows],
        }
        for r in rows:
            amount = float(r["pago_monto"] or 0)
            method = (r["pago_metodo"] or "").lower()
            if "efectivo" in method:
                summary["cash_collected"] += amount
            elif "tarjeta" in method:
                summary["card_collected"] += amount
            elif "transfer" in method:
                summary["transfer_collected"] += amount
            elif "sin cobro" in method or "online" in method:
                amount = 0.0
            summary["total_collected"] += amount
        return summary

    def create_driver_cut(self, data: Dict[str, Any]) -> int:
        cur = self.db.execute(
            """
            INSERT INTO delivery_driver_cuts(
                driver_id, driver_nombre, turno_inicio, turno_fin, entregas_total,
                efectivo_cobrado, tarjeta_cobrado, transfer_cobrado, total_cobrado,
                efectivo_entregado, diferencia, usuario_corte, sucursal_id, notas, fecha
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
            """,
            (
                data.get("driver_id"), data.get("driver_nombre"), data.get("turno_inicio"),
                data.get("turno_fin"), data.get("entregas_total", 0),
                data.get("efectivo_cobrado", 0), data.get("tarjeta_cobrado", 0),
                data.get("transfer_cobrado", 0), data.get("total_cobrado", 0),
                data.get("efectivo_entregado", 0), data.get("diferencia", 0),
                data.get("usuario_corte"), data.get("sucursal_id", 1), data.get("notas", ""),
            ),
        )
        self.db.commit()
        return int(cur.lastrowid)
