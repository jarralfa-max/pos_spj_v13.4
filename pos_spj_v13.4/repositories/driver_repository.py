from __future__ import annotations


class DriverRepository:
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id INTEGER,
                lat REAL,
                lng REAL,
                fecha DATETIME DEFAULT (datetime('now'))
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_driver_cuts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id INTEGER NOT NULL,
                driver_nombre TEXT NOT NULL,
                turno_inicio DATETIME,
                turno_fin DATETIME,
                entregas_total INTEGER DEFAULT 0,
                efectivo_cobrado REAL DEFAULT 0,
                tarjeta_cobrado REAL DEFAULT 0,
                transfer_cobrado REAL DEFAULT 0,
                total_cobrado REAL DEFAULT 0,
                efectivo_entregado REAL DEFAULT 0,
                diferencia REAL DEFAULT 0,
                usuario_corte TEXT,
                sucursal_id INTEGER,
                notas TEXT,
                fecha DATETIME DEFAULT (datetime('now'))
            )
            """
        )
        try:
            self.db.commit()
        except Exception:
            pass

    def list_active_drivers(self, branch_id: int) -> list[dict]:
        rows = self.db.execute(
            "SELECT id,nombre,telefono,vehiculo,activo,en_ruta,sucursal_id,usuario_id "
            "FROM drivers WHERE activo=1 AND COALESCE(sucursal_id,1)=? ORDER BY nombre",
            (int(branch_id),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_driver(self, driver_id: int):
        row = self.db.execute("SELECT * FROM drivers WHERE id=?", (int(driver_id),)).fetchone()
        return dict(row) if row else None

    def assign_driver(self, order_id: int, driver_id: int) -> None:
        self.db.execute(
            "UPDATE delivery_orders SET driver_id=?, fecha_asignacion=datetime('now') WHERE id=?",
            (int(driver_id), int(order_id)),
        )
        self.db.commit()

