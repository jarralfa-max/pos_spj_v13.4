# core/services/anticipo_service.py — SPJ POS v13
"""
Motor de cálculo de anticipos para cotizaciones.

Reglas evaluadas en orden:
  1. Exenciones (cliente con crédito / nivel fidelidad / monto mínimo)
  2. Reglas por categoría de producto
  3. Reglas por monto total
  4. Criterio de combinación: maximo | minimo | suma (configurable)
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger("spj.anticipo")


class AnticipoCotizacionService:

    def __init__(self, db_conn):
        self.db = db_conn
        self._config_cache: dict = {}
        self._rules_cache: list = []
        self._cache_ts: float = 0

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        import time
        now = time.time()
        if now - self._cache_ts > 120:
            try:
                rows = self.db.execute(
                    "SELECT clave, valor FROM anticipo_config"
                ).fetchall()
                self._config_cache = {r[0]: r[1] for r in rows}
                rows2 = self.db.execute(
                    "SELECT tipo, categoria, monto_desde, monto_hasta, pct_anticipo "
                    "FROM anticipo_reglas WHERE activo=1 ORDER BY tipo, monto_desde"
                ).fetchall()
                self._rules_cache = [dict(r) for r in rows2]
            except Exception as e:
                logger.debug("_load_config: %s", e)
            self._cache_ts = now
        return self._config_cache

    def invalidar_cache(self):
        self._cache_ts = 0

    def get_config(self, clave: str, default: str = "") -> str:
        return self._load_config().get(clave, default)

    # ── Cálculo principal ─────────────────────────────────────────────────────

    def calcular(self, total: float, items: list,
                 cliente_id: Optional[int] = None,
                 nivel_fidelidad: str = "Bronce") -> dict:
        """
        Calcula el anticipo requerido para una cotización.

        Args:
            total:           Monto total de la cotización
            items:           Lista de {'categoria': str, 'subtotal': float, ...}
            cliente_id:      ID del cliente (para verificar crédito aprobado)
            nivel_fidelidad: Nivel de fidelidad del cliente

        Returns:
            {
              'requiere': bool,
              'pct': float,          # porcentaje aplicado
              'monto': float,        # monto en pesos
              'razon': str,          # explicación
              'exento': bool,
            }
        """
        cfg = self._load_config()

        # ── 1. Verificar exenciones ───────────────────────────────────────────
        # 1a. Cliente con crédito aprobado
        if cliente_id:
            try:
                row = self.db.execute(
                    "SELECT allows_credit FROM clientes WHERE id=?",
                    (cliente_id,)
                ).fetchone()
                if row and row[0]:
                    return self._exento("Cliente con crédito aprobado")
            except Exception:
                pass

        # 1b. Nivel de fidelidad exento
        niveles_exentos = [n.strip() for n in
                           cfg.get("niveles_exentos", "").split(",") if n.strip()]
        if nivel_fidelidad in niveles_exentos:
            return self._exento(f"Nivel {nivel_fidelidad} exento de anticipo")

        # 1c. Monto por debajo del mínimo
        monto_minimo = float(cfg.get("monto_minimo", 500))
        if total < monto_minimo:
            return self._exento(f"Monto ${total:.2f} menor al mínimo ${monto_minimo:.0f}")

        # ── 2. Calcular por categoría ─────────────────────────────────────────
        pct_cat = 0.0
        cat_ganadora = ""
        reglas_cat = [r for r in self._rules_cache if r["tipo"] == "categoria"]

        for item in items:
            cat = item.get("categoria", "")
            for regla in reglas_cat:
                if regla.get("categoria", "").lower() == cat.lower():
                    if regla["pct_anticipo"] > pct_cat:
                        pct_cat = regla["pct_anticipo"]
                        cat_ganadora = cat

        # Usar default si no hay regla de categoría
        if pct_cat == 0 and reglas_cat:
            pct_cat = float(cfg.get("pct_default", 30))

        # ── 3. Calcular por monto ──────────────────────────────────────────────
        pct_monto = 0.0
        reglas_monto = sorted(
            [r for r in self._rules_cache if r["tipo"] == "monto"],
            key=lambda x: x.get("monto_desde", 0)
        )
        for regla in reglas_monto:
            desde = float(regla.get("monto_desde", 0) or 0)
            hasta = regla.get("monto_hasta")
            if total >= desde and (hasta is None or total <= float(hasta)):
                pct_monto = float(regla["pct_anticipo"])

        # ── 4. Aplicar criterio de combinación ────────────────────────────────
        criterio = cfg.get("criterio_combinacion", "maximo")
        if criterio == "maximo":
            pct_final = max(pct_cat, pct_monto)
            razon_criterio = f"mayor(cat={pct_cat:.0f}%,monto={pct_monto:.0f}%)={pct_final:.0f}%"
        elif criterio == "minimo":
            pct_final = min(pct_cat, pct_monto) if (pct_cat > 0 and pct_monto > 0) else max(pct_cat, pct_monto)
            razon_criterio = f"menor(cat={pct_cat:.0f}%,monto={pct_monto:.0f}%)={pct_final:.0f}%"
        else:  # suma, con tope en 80%
            pct_final = min(pct_cat + pct_monto, 80)
            razon_criterio = f"suma(cat={pct_cat:.0f}%+monto={pct_monto:.0f}%)={pct_final:.0f}%"

        if pct_final <= 0:
            return self._exento("Sin reglas aplicables para este pedido")

        monto = round(total * pct_final / 100, 2)
        razon_parts = []
        if cat_ganadora:
            razon_parts.append(f"Categoría '{cat_ganadora}' ({pct_cat:.0f}%)")
        if pct_monto > 0:
            razon_parts.append(f"Monto ${total:.0f} ({pct_monto:.0f}%)")
        razon_parts.append(f"Criterio: {criterio} → {pct_final:.0f}%")

        return {
            "requiere": True,
            "pct":      pct_final,
            "monto":    monto,
            "razon":    " | ".join(razon_parts),
            "exento":   False,
        }

    def _exento(self, razon: str) -> dict:
        return {"requiere": False, "pct": 0.0, "monto": 0.0,
                "razon": razon, "exento": True}

    # ── Admin CRUD ────────────────────────────────────────────────────────────

    def set_config(self, clave: str, valor: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO anticipo_config(clave,valor) VALUES(?,?)",
            (clave, str(valor)))
        try: self.db.commit()
        except Exception: pass
        self.invalidar_cache()

    def get_reglas(self) -> list:
        try:
            rows = self.db.execute(
                "SELECT * FROM anticipo_reglas ORDER BY tipo, monto_desde"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def save_regla(self, tipo: str, categoria: str = None,
                   monto_desde: float = 0, monto_hasta: float = None,
                   pct: float = 30, notas: str = "") -> int:
        rid = self.db.execute("""
            INSERT INTO anticipo_reglas
                (tipo, categoria, monto_desde, monto_hasta, pct_anticipo, notas)
            VALUES (?,?,?,?,?,?)
        """, (tipo, categoria, monto_desde, monto_hasta, pct, notas)).lastrowid
        try: self.db.commit()
        except Exception: pass
        self.invalidar_cache()
        return rid

    def delete_regla(self, regla_id: int) -> None:
        self.db.execute("DELETE FROM anticipo_reglas WHERE id=?", (regla_id,))
        try: self.db.commit()
        except Exception: pass
        self.invalidar_cache()

    # ── Órdenes de cotización ─────────────────────────────────────────────────

    def crear_orden(self, cotizacion_id: int, cliente_id: int,
                    sucursal_id: int, fecha_entrega: str,
                    hora_entrega: str, tipo_entrega: str,
                    usuario: str, anticipo_info: dict,
                    notas: str = "") -> dict:
        """Crea una orden a partir de una cotización confirmada."""
        import uuid as _uuid
        numero = f"ORD-{_uuid.uuid4().hex[:6].upper()}"
        self.db.execute("""
            INSERT INTO ordenes_cotizacion
                (numero_orden, cotizacion_id, cliente_id, sucursal_id,
                 estado, requiere_anticipo, pct_anticipo_aplicado,
                 razon_anticipo, monto_anticipo, fecha_entrega,
                 hora_entrega, tipo_entrega, notas, usuario_asigno)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            numero, cotizacion_id, cliente_id, sucursal_id,
            "anticipo_pendiente" if anticipo_info["requiere"] else "en_preparacion",
            int(anticipo_info["requiere"]),
            anticipo_info["pct"],
            anticipo_info["razon"],
            anticipo_info["monto"],
            fecha_entrega, hora_entrega, tipo_entrega,
            notas, usuario
        ))
        try: self.db.commit()
        except Exception: pass
        return {"numero_orden": numero, "anticipo": anticipo_info}

    def get_orden(self, numero_orden: str) -> dict | None:
        try:
            row = self.db.execute(
                "SELECT * FROM ordenes_cotizacion WHERE numero_orden=?",
                (numero_orden,)
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def registrar_anticipo_pagado(self, numero_orden: str,
                                   monto: float, metodo: str,
                                   payment_id: str = "") -> None:
        orden = self.get_orden(numero_orden)
        if not orden: return
        nuevo_estado = (
            "en_preparacion"
            if (orden["anticipo_pagado"] + monto) >= orden["monto_anticipo"] - 0.01
            else "anticipo_pendiente"
        )
        self.db.execute("""
            UPDATE ordenes_cotizacion
            SET anticipo_pagado = anticipo_pagado + ?,
                metodo_anticipo = ?,
                payment_id      = ?,
                estado          = ?
            WHERE numero_orden = ?
        """, (monto, metodo, payment_id, nuevo_estado, numero_orden))
        try: self.db.commit()
        except Exception: pass

    def get_ordenes_pendientes_recordatorio(self, dias: int) -> list:
        """Retorna órdenes cuyo recordatorio D-N aún no fue enviado."""
        # Whitelist: solo dias 1 o 2 para evitar injection
        if dias not in (1, 2):
            return []
        campo = f"recordatorio_d{dias}_enviado"
        try:
            query = (
                "SELECT * FROM ordenes_cotizacion "
                "WHERE estado NOT IN ('entregado','cancelado') "
                "  AND " + campo + " = 0 "
                "  AND date(fecha_entrega) = date('now', '+' || ? || ' days')"
            )
            rows = self.db.execute(query, (dias,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
