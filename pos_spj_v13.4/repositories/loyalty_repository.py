from __future__ import annotations

from typing import Any, Dict, List, Optional


class LoyaltyRepository:
    """Repositorio SQL de fidelización (FASE 2)."""

    def __init__(self, db_conn):
        self.db = db_conn

    # ──────────────────────────────────────────────────────────────────
    # Ledger canónico
    # ──────────────────────────────────────────────────────────────────
    def get_balance(self, cliente_id: int) -> int:
        row = self.db.execute(
            "SELECT COALESCE(SUM(puntos),0) FROM loyalty_ledger WHERE cliente_id=?",
            (cliente_id,),
        ).fetchone()
        return int((row[0] if row else 0) or 0)

    def ledger_exists(self, cliente_id: int, tipo: str, referencia: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM loyalty_ledger WHERE cliente_id=? AND tipo=? AND referencia=? LIMIT 1",
            (cliente_id, tipo, str(referencia or "")),
        ).fetchone()
        return bool(row)

    def append_ledger_entry(
        self,
        *,
        cliente_id: int,
        tipo: str,
        puntos: int,
        referencia: str,
        descripcion: str = "",
        sucursal_id: int = 1,
        usuario: str = "",
        monto_equiv: float = 0.0,
    ) -> bool:
        if self.ledger_exists(cliente_id, tipo, referencia):
            return False
        saldo_post = self.get_balance(cliente_id) + int(puntos)
        self.db.execute(
            """
            INSERT INTO loyalty_ledger
            (cliente_id, tipo, puntos, monto_equiv, saldo_post, referencia, descripcion, sucursal_id, usuario)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                cliente_id,
                tipo,
                int(puntos),
                float(monto_equiv),
                saldo_post,
                str(referencia or ""),
                str(descripcion or ""),
                int(sucursal_id),
                str(usuario or ""),
            ),
        )
        return True

    # ──────────────────────────────────────────────────────────────────
    # Consultas resumen
    # ──────────────────────────────────────────────────────────────────
    def get_customer_summary(self, cliente_id: int) -> Dict[str, Any]:
        has_tel = False
        try:
            cols = self.db.execute("PRAGMA table_info(clientes)").fetchall()
            has_tel = any((c[1] if isinstance(c, tuple) else c["name"]) == 'telefono' for c in cols)
        except Exception:
            has_tel = False
        sql = "SELECT id, nombre, COALESCE(puntos,0) AS puntos_snapshot"
        if has_tel:
            sql += ", telefono"
        sql += " FROM clientes WHERE id=?"
        cliente = self.db.execute(sql, (cliente_id,)).fetchone()
        saldo = self.get_balance(cliente_id)

        if isinstance(cliente, tuple):
            nombre = cliente[1] if cliente else ""
            snap = int(cliente[2]) if cliente else 0
            tel = (cliente[3] if (cliente and len(cliente) > 3) else "")
        else:
            nombre = cliente["nombre"] if cliente else ""
            snap = int(cliente["puntos_snapshot"]) if cliente else 0
            tel = (cliente["telefono"] if (cliente and "telefono" in cliente.keys()) else "")

        return {
            "cliente_id": cliente_id,
            "nombre": nombre,
            "telefono": tel,
            "saldo_ledger": saldo,
            "puntos_snapshot": snap,
            "snapshot_diff": saldo - snap,
        }

    # ──────────────────────────────────────────────────────────────────
    # Referidos/config
    # ──────────────────────────────────────────────────────────────────
    def get_referral_config(self) -> Dict[str, Any]:
        keys_defaults = {
            "ref_bono_referidor": "50",
            "ref_bono_referido": "25",
            "ref_max_mensual": "10",
        }
        out: Dict[str, Any] = {}
        for k, default in keys_defaults.items():
            r = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (k,)
            ).fetchone()
            raw = (r[0] if r else default)
            out[k] = int(raw or default)
        return out

    def save_referral_config(self, referidor: int, referido: int, max_mensual: int) -> None:
        for k, v in [
            ("ref_bono_referidor", int(referidor)),
            ("ref_bono_referido", int(referido)),
            ("ref_max_mensual", int(max_mensual)),
        ]:
            self.db.execute(
                "INSERT INTO configuraciones(clave,valor) VALUES(?,?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (k, str(v)),
            )

    def list_referrals(self, limit: int = 50) -> List[Any]:
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS referidos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referidor_id INTEGER,
                referido_id INTEGER,
                bono_dado INTEGER DEFAULT 0,
                estado TEXT DEFAULT 'pendiente',
                fecha DATETIME DEFAULT (datetime('now'))
            )
            """
        )
        return self.db.execute(
            """
            SELECT r.fecha, c1.nombre AS referidor, c2.nombre AS referido, r.bono_dado, r.estado
            FROM referidos r
            LEFT JOIN clientes c1 ON c1.id=r.referidor_id
            LEFT JOIN clientes c2 ON c2.id=r.referido_id
            ORDER BY r.fecha DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    # ──────────────────────────────────────────────────────────────────
    # Cumpleaños / retención
    # ──────────────────────────────────────────────────────────────────
    def list_upcoming_birthdays(self, days: int = 7) -> List[Any]:
        days = max(1, int(days))
        return self.db.execute(
            f"""
            SELECT c.nombre,
                   c.fecha_nacimiento,
                   c.telefono,
                   COALESCE((
                       SELECT nivel FROM tarjetas_fidelidad tf
                        WHERE (tf.id_cliente=c.id OR tf.cliente_id=c.id)
                        LIMIT 1
                   ), 'Sin tarjeta') AS nivel
            FROM clientes c
            WHERE c.fecha_nacimiento IS NOT NULL
              AND strftime('%m-%d', c.fecha_nacimiento)
                  BETWEEN strftime('%m-%d', 'now') AND strftime('%m-%d', 'now', '+{days} days')
              AND COALESCE(c.activo,1)=1
            ORDER BY strftime('%m-%d', c.fecha_nacimiento)
            """
        ).fetchall()

    def list_at_risk_customers(self, days_without_sale: int = 30, limit: int = 200) -> List[Any]:
        days_without_sale = max(1, int(days_without_sale))
        return self.db.execute(
            """
            SELECT c.nombre,
                   MAX(v.fecha) as ultima,
                   CAST(julianday('now') - julianday(MAX(v.fecha)) AS INTEGER) as dias_inactivo,
                   COALESCE(SUM(v.total), 0) as total_hist,
                   c.telefono
            FROM clientes c
            LEFT JOIN ventas v ON v.cliente_id = c.id
            WHERE COALESCE(c.activo,1)=1
            GROUP BY c.id
            HAVING dias_inactivo >= ? OR ultima IS NULL
            ORDER BY dias_inactivo DESC
            LIMIT ?
            """,
            (days_without_sale, int(limit)),
        ).fetchall()


    def get_config_value(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT valor FROM configuraciones WHERE clave=?", (str(key),)).fetchone()
        if not row:
            return default
        return (row[0] if isinstance(row, tuple) else row["valor"]) or default

    def set_config_values(self, kv: dict) -> None:
        for k, v in (kv or {}).items():
            self.db.execute(
                "INSERT INTO configuraciones(clave,valor) VALUES(?,?) ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (str(k), str(v)),
            )
    # ──────────────────────────────────────────────────────────────────
    # Tarjetas
    # ──────────────────────────────────────────────────────────────────
    def assign_card(self, cliente_id: int, codigo: str) -> None:
        self.db.execute(
            """
            UPDATE tarjetas_fidelidad
               SET cliente_id = ?,
                   id_cliente = COALESCE(id_cliente, ?),
                   estado = 'asignada'
             WHERE codigo = ?
            """,
            (int(cliente_id), int(cliente_id), str(codigo)),
        )

    def block_card(self, codigo: str) -> None:
        self.db.execute(
            "UPDATE tarjetas_fidelidad SET estado='bloqueada' WHERE codigo=?",
            (str(codigo),),
        )

    def get_card_by_code(self, codigo: str) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            """
            SELECT id, codigo,
                   COALESCE(cliente_id, id_cliente) AS cliente_id,
                   estado, COALESCE(nivel,'Bronce') AS nivel,
                   COALESCE(puntos_actuales, puntos, 0) AS puntos_actuales
            FROM tarjetas_fidelidad
            WHERE codigo=?
            LIMIT 1
            """,
            (str(codigo),),
        ).fetchone()
        if not row:
            return None
        if isinstance(row, tuple):
            return {
                "id": row[0],
                "codigo": row[1],
                "cliente_id": row[2],
                "estado": row[3],
                "nivel": row[4],
                "puntos_actuales": row[5],
            }
        return dict(row)
