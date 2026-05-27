from __future__ import annotations

from typing import Any, Dict, List, Optional
import hashlib
import random


class LoyaltyRepository:
    """Repositorio SQL de fidelización (FASE 2)."""
    RAFFLE_TABLES = ("raffles", "raffle_tickets", "raffle_winners", "raffle_financial_ledger")

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
        self.ensure_referrals_table()
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

    def ensure_referrals_table(self) -> None:
        # TODO: mover este DDL a migración formal cuando el bootstrap de migraciones
        # de fidelidad quede consolidado en todos los entornos.
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

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        if row is None:
            return {}
        if isinstance(row, tuple):
            return {}
        return dict(row)

    def ensure_raffle_tables(self) -> None:
        """Bootstrap temporal de esquema de rifas/sorteos con guardas financieras.

        TODO: migrar este DDL a migraciones formales versionadas.
        """
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS raffles(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                premio TEXT DEFAULT '',
                premio_costo_estimado REAL DEFAULT 0,
                presupuesto_maximo REAL DEFAULT 0,
                ventas_objetivo REAL DEFAULT 0,
                roi_objetivo REAL DEFAULT 0,
                monto_por_boleto REAL DEFAULT 0,
                max_boletos_por_cliente INTEGER DEFAULT 1,
                estado TEXT DEFAULT 'borrador',
                financial_status TEXT DEFAULT 'presupuestada',
                fecha_inicio TEXT,
                fecha_fin TEXT,
                sucursal_id INTEGER DEFAULT 1,
                created_by TEXT DEFAULT '',
                approved_by TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS raffle_tickets(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raffle_id INTEGER NOT NULL,
                cliente_id INTEGER,
                venta_id INTEGER,
                folio_venta TEXT,
                numero_boleto TEXT NOT NULL,
                monto_base REAL DEFAULT 0,
                estado TEXT DEFAULT 'vigente',
                cancel_reason TEXT DEFAULT '',
                sucursal_id INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                cancelled_at TEXT,
                UNIQUE(raffle_id, numero_boleto),
                UNIQUE(raffle_id, venta_id, numero_boleto)
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS raffle_financial_ledger(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raffle_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                monto REAL DEFAULT 0,
                referencia TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                usuario TEXT DEFAULT '',
                sucursal_id INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(raffle_id, tipo, referencia)
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS raffle_winners(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raffle_id INTEGER NOT NULL,
                ticket_id INTEGER NOT NULL,
                cliente_id INTEGER,
                premio TEXT DEFAULT '',
                premio_costo_real REAL DEFAULT 0,
                estado_entrega TEXT DEFAULT 'pendiente',
                seleccionado_por TEXT DEFAULT '',
                random_seed TEXT DEFAULT '',
                pool_hash TEXT DEFAULT '',
                fecha_seleccion TEXT DEFAULT (datetime('now')),
                fecha_entrega TEXT,
                notificado INTEGER DEFAULT 0,
                UNIQUE(raffle_id, ticket_id)
            )
            """
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_raffles_estado_fecha ON raffles(estado, created_at)"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_raffle_tickets_raffle ON raffle_tickets(raffle_id, estado)"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_raffle_winners_raffle ON raffle_winners(raffle_id, estado_entrega)"
        )
    def create_raffle(self, data: Dict[str, Any]) -> int:
        self.ensure_raffle_tables()
        payload = {
            "nombre": str(data.get("nombre") or "").strip(),
            "descripcion": str(data.get("descripcion") or ""),
            "premio": str(data.get("premio") or ""),
            "premio_costo_estimado": float(data.get("premio_costo_estimado") or 0),
            "presupuesto_maximo": float(data.get("presupuesto_maximo") or 0),
            "ventas_objetivo": float(data.get("ventas_objetivo") or 0),
            "roi_objetivo": float(data.get("roi_objetivo") or 0),
            "monto_por_boleto": float(data.get("monto_por_boleto") or 0),
            "max_boletos_por_cliente": int(data["max_boletos_por_cliente"]) if "max_boletos_por_cliente" in data and data.get("max_boletos_por_cliente") is not None else 999999,
            "estado": str(data.get("estado") or "borrador"),
            "financial_status": str(data.get("financial_status") or "presupuestada"),
            "fecha_inicio": data.get("fecha_inicio"),
            "fecha_fin": data.get("fecha_fin"),
            "sucursal_id": int(data.get("sucursal_id") or 1),
            "created_by": str(data.get("created_by") or ""),
            "approved_by": str(data.get("approved_by") or ""),
        }
        if not payload["nombre"]:
            raise ValueError("nombre de rifa requerido")
        cols = tuple(payload.keys())
        vals = [payload[c] for c in cols]
        self.db.execute(
            f"INSERT INTO raffles ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
            vals,
        )
        row = self.db.execute("SELECT last_insert_rowid()").fetchone()
        return int((row[0] if row else 0) or 0)

    def get_raffle_by_id(self, raffle_id: int) -> Dict[str, Any]:
        self.ensure_raffle_tables()
        row = self.db.execute("SELECT * FROM raffles WHERE id=?", (int(raffle_id),)).fetchone()
        return self._row_to_dict(row)

    def reserve_raffle_budget(
        self,
        raffle_id: int,
        monto: float,
        usuario: str,
        referencia: str,
    ) -> bool:
        self.ensure_raffle_tables()
        raffle = self.get_raffle_by_id(raffle_id)
        if not raffle:
            raise ValueError("rifa inexistente")
        if not referencia:
            raise ValueError("referencia requerida")
        monto_value = float(monto or 0)
        if monto_value <= 0:
            raise ValueError("monto de reserva inválido")
        try:
            self.db.execute(
                """
                INSERT INTO raffle_financial_ledger
                (raffle_id, tipo, monto, referencia, descripcion, usuario, sucursal_id)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    int(raffle_id),
                    "reserva",
                    monto_value,
                    str(referencia),
                    "Reserva presupuesto rifa",
                    str(usuario or ""),
                    int(raffle.get("sucursal_id") or 1),
                ),
            )
        except Exception:
            return False
        self.db.execute(
            "UPDATE raffles SET financial_status='reservada',updated_at=datetime('now') WHERE id=?",
            (int(raffle_id),),
        )
        return True

    def activate_raffle(self, raffle_id: int, usuario: str) -> bool:
        cur = self.db.execute(
            """
            UPDATE raffles
               SET estado='activa', approved_by=?, updated_at=datetime('now')
             WHERE id=?
            """,
            (str(usuario or ""), int(raffle_id)),
        )
        return int(getattr(cur, "rowcount", 0) or 0) > 0

    def close_raffle(self, raffle_id: int, usuario: str) -> bool:
        cur = self.db.execute(
            """
            UPDATE raffles
               SET estado='cerrada', approved_by=COALESCE(NULLIF(approved_by,''), ?), updated_at=datetime('now')
             WHERE id=?
            """,
            (str(usuario or ""), int(raffle_id)),
        )
        return int(getattr(cur, "rowcount", 0) or 0) > 0

    def generate_tickets_for_sale(
        self,
        raffle_id: int,
        venta_id: int,
        cliente_id: int,
        folio_venta: str,
        monto_base: float,
        sucursal_id: int,
    ) -> List[str]:
        raffle = self.get_raffle_by_id(raffle_id)
        if not raffle:
            raise ValueError("rifa inexistente")
        ticket_amount = float(raffle.get("monto_por_boleto") or 0)
        if ticket_amount <= 0:
            raise ValueError("monto_por_boleto inválido")
        tickets_count = max(1, int(float(monto_base or 0) / ticket_amount))
        max_per_customer = int(raffle.get("max_boletos_por_cliente") or tickets_count)
        tickets_count = min(tickets_count, max(1, max_per_customer))

        created: List[str] = []
        for i in range(tickets_count):
            ticket_number = f"{int(raffle_id)}-{int(venta_id)}-{i + 1}"
            try:
                self.db.execute(
                    """
                    INSERT INTO raffle_tickets
                    (raffle_id, cliente_id, venta_id, folio_venta, numero_boleto, monto_base, estado, sucursal_id)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        int(raffle_id),
                        int(cliente_id),
                        int(venta_id),
                        str(folio_venta or ""),
                        ticket_number,
                        float(monto_base or 0),
                        "vigente",
                        int(sucursal_id or 1),
                    ),
                )
                created.append(ticket_number)
            except Exception:
                continue
        return created

    def cancel_tickets_for_sale(self, venta_id: int, reason: str) -> int:
        cur = self.db.execute(
            """
            UPDATE raffle_tickets
               SET estado='cancelado',
                   cancel_reason=?,
                   cancelled_at=datetime('now')
             WHERE venta_id=? AND estado<>'cancelado'
            """,
            (str(reason or "cancelación de venta"), int(venta_id)),
        )
        return int(getattr(cur, "rowcount", 0) or 0)

    def select_winner(
        self,
        raffle_id: int,
        usuario: str,
        random_seed: Optional[str] = None,
    ) -> Dict[str, Any]:
        seed = str(random_seed or random.random())
        tickets = self.db.execute(
            """
            SELECT id, cliente_id, numero_boleto
              FROM raffle_tickets
             WHERE raffle_id=? AND estado='vigente'
             ORDER BY id
            """,
            (int(raffle_id),),
        ).fetchall()
        if not tickets:
            return {}

        pool = "|".join(str(t[2] if isinstance(t, tuple) else t["numero_boleto"]) for t in tickets)
        index = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(tickets)
        winner = tickets[index]
        ticket_id = winner[0] if isinstance(winner, tuple) else winner["id"]
        cliente_id = winner[1] if isinstance(winner, tuple) else winner["cliente_id"]
        pool_hash = hashlib.sha256(pool.encode()).hexdigest()

        self.db.execute(
            """
            INSERT OR IGNORE INTO raffle_winners
            (raffle_id, ticket_id, cliente_id, premio, seleccionado_por, random_seed, pool_hash)
            SELECT id, ?, ?, premio, ?, ?, ? FROM raffles WHERE id=?
            """,
            (ticket_id, cliente_id, str(usuario or ""), seed, pool_hash, int(raffle_id)),
        )
        return {
            "raffle_id": int(raffle_id),
            "ticket_id": int(ticket_id),
            "cliente_id": int(cliente_id or 0),
            "random_seed": seed,
            "pool_hash": pool_hash,
        }

    def mark_prize_delivered(self, winner_id: int, usuario: str, costo_real: float) -> bool:
        cur = self.db.execute(
            """
            UPDATE raffle_winners
               SET estado_entrega='entregado',
                   premio_costo_real=?,
                   fecha_entrega=datetime('now')
             WHERE id=? AND estado_entrega<>'entregado'
            """,
            (float(costo_real or 0), int(winner_id)),
        )
        return int(getattr(cur, "rowcount", 0) or 0) > 0

    def list_raffles(self, limit: int = 50) -> List[Any]:
        self.ensure_raffle_tables()
        return self.db.execute("""
            SELECT r.id, r.nombre, r.premio, r.estado, r.financial_status, r.fecha_inicio, r.fecha_fin,
                   COALESCE((SELECT COUNT(*) FROM raffle_tickets t WHERE t.raffle_id=r.id AND t.estado='vigente'),0) AS boletos_emitidos,
                   COALESCE(r.presupuesto_maximo,0) AS presupuesto
            FROM raffles r ORDER BY r.created_at DESC LIMIT ?
            """,(int(limit),)).fetchall()

    def get_raffle_summary(self) -> Dict[str, int]:
        self.ensure_raffle_tables()
        q=self.db.execute
        return {
            "rifas_activas": int((q("SELECT COUNT(*) FROM raffles WHERE estado='activa'").fetchone() or [0])[0] or 0),
            "boletos_emitidos": int((q("SELECT COUNT(*) FROM raffle_tickets WHERE estado='vigente'").fetchone() or [0])[0] or 0),
            "boletos_cancelados": int((q("SELECT COUNT(*) FROM raffle_tickets WHERE estado='cancelado'").fetchone() or [0])[0] or 0),
            "premios_pendientes": int((q("SELECT COUNT(*) FROM raffle_winners WHERE estado_entrega='pendiente'").fetchone() or [0])[0] or 0),
            "pasivo_promocional": float((q("SELECT COALESCE(SUM(monto),0) FROM raffle_financial_ledger WHERE tipo='reserva'").fetchone() or [0])[0] or 0),
            "presupuesto_usado": float((q("SELECT COALESCE(SUM(premio_costo_real),0) FROM raffle_winners WHERE estado_entrega='entregado'").fetchone() or [0])[0] or 0),
            "roi_estimado": 0.0,
        }


    def get_dashboard_kpis(self) -> Dict[str, Any]:
        self.ensure_raffle_tables()
        q=self.db.execute
        def _safe_scalar(sql: str, default: int = 0) -> int:
            try:
                row = q(sql).fetchone()
                return int((row[0] if row else default) or default)
            except Exception:
                return int(default)
        clientes_con_puntos = _safe_scalar("SELECT COUNT(*) FROM clientes WHERE COALESCE(puntos,0)>0")
        puntos_activos = _safe_scalar("SELECT COALESCE(SUM(puntos),0) FROM loyalty_ledger")
        emitidos_mes = _safe_scalar("SELECT COALESCE(SUM(CASE WHEN tipo='acumulacion' THEN puntos ELSE 0 END),0) FROM loyalty_ledger")
        canjeados_mes = _safe_scalar("SELECT ABS(COALESCE(SUM(CASE WHEN tipo='canje' THEN puntos ELSE 0 END),0)) FROM loyalty_ledger")
        valor_estrella = float(self.get_config_value("loyalty_valor_estrella", "0.10") or 0.10)
        return {"clientes_con_puntos":clientes_con_puntos,"puntos_activos":puntos_activos,"pasivo_operativo":float(puntos_activos*valor_estrella),"puntos_emitidos_mes":emitidos_mes,"puntos_canjeados_mes":canjeados_mes,"cumples_7_dias":0,"clientes_en_riesgo":0,"rifas_activas":self.get_raffle_summary().get("rifas_activas",0)}

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
