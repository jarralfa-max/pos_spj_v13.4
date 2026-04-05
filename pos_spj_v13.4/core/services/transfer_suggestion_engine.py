
# core/services/transfer_suggestion_engine.py — SPJ POS v12
# ── Motor de Sugerencias de Transferencia ─────────────────────────────────────
#
# MÉTODO MATEMÁTICO: Días de Suministro (DOS) + Coeficiente de Variación (CV)
#
# Algoritmo en 4 pasos:
#
#   1. VELOCIDAD DE VENTA (Sales Velocity)
#      v_i = Σqty_vendida(30d) / 30  → unidades/día por producto por sucursal
#      Usa suavizado exponencial (α=0.3) para reducir ruido de días atípicos.
#
#   2. DÍAS DE SUMINISTRO (Days of Supply, DOS)
#      DOS_i = stock_actual_i / v_i
#      Ejemplo: 50 kg stock / 5 kg/día = 10 días de suministro.
#      Si v_i = 0 (sin ventas) → DOS = ∞ → candidato a transferir.
#
#   3. DETECCIÓN DE DESEQUILIBRIO (Coeficiente de Variación entre sucursales)
#      CV = σ(DOS) / μ(DOS)  donde σ = desv. estándar, μ = media aritmética.
#      CV > 0.40 → desequilibrio significativo → generar sugerencia.
#      Usando IQR como respaldo para datasets pequeños (< 4 sucursales).
#
#   4. CÁLCULO DE TRANSFERENCIA ÓPTIMA
#      Para cada par (sucursal_exceso, sucursal_deficit):
#        qty_sugerida = min(
#            (DOS_origen - DOS_objetivo) × v_origen,   # excedente disponible
#            (DOS_objetivo - DOS_destino) × v_destino,  # déficit a cubrir
#        )
#      DOS_objetivo = mediana(DOS) de todas las sucursales para ese producto.
#
#   SCORE DE URGENCIA (0–100):
#      score = 100 × (1 - DOS_destino / DOS_objetivo)
#      Cuanto más cerca de cero esté el stock del destino, mayor urgencia.
#
# FUENTES DE DATOS:
#   stock   → inventario_actual (producto_id, sucursal_id, cantidad)
#             fallback: branch_inventory (branch_id, product_id, quantity)
#   ventas  → detalles_venta JOIN ventas (últimos 30 días, por sucursal)
#   sucursales → tabla sucursales (activa=1)
#
from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("spj.transfer_suggestion")

# ── Umbrales configurables ─────────────────────────────────────────────────────
DEFAULT_WINDOW_DAYS      = 30    # ventana histórica de ventas
DEFAULT_DOS_MIN          = 5.0   # días mínimos aceptables en destino
DEFAULT_DOS_TARGET_MULT  = 1.5   # objetivo = mediana × multiplicador
DEFAULT_CV_THRESHOLD     = 0.40  # CV > 40% = desequilibrio relevante
DEFAULT_MIN_QTY_KG       = 0.5   # transferencia mínima sugerida
DEFAULT_MIN_SCORE        = 20.0  # urgencia mínima para incluir sugerencia


# ── DTOs ───────────────────────────────────────────────────────────────────────

@dataclass
class BranchStockInfo:
    """Stock y velocidad de venta de un producto en una sucursal."""
    branch_id:   int
    branch_name: str
    product_id:  int
    stock:       float        # kg / unidades actuales
    velocity:    float        # unidades/día (promedio últimos N días)
    dos:         float        # días de suministro = stock / velocity
    sales_30d:   float        # ventas brutas últimos 30 días


@dataclass
class TransferSuggestion:
    """Sugerencia de transferencia entre dos sucursales para un producto."""
    product_id:       int
    product_name:     str
    product_unit:     str
    origin_branch_id: int
    origin_name:      str
    origin_stock:     float
    origin_dos:       float
    dest_branch_id:   int
    dest_name:        str
    dest_stock:       float
    dest_dos:         float
    qty_suggested:    float    # cantidad recomendada a transferir
    urgency_score:    float    # 0–100 (100 = crítico)
    reason:           str      # explicación legible
    cv:               float    # coeficiente de variación del producto

    def to_dict(self) -> dict:
        return {
            "product_id":       self.product_id,
            "product_name":     self.product_name,
            "product_unit":     self.product_unit,
            "origin_branch_id": self.origin_branch_id,
            "origin_name":      self.origin_name,
            "origin_stock":     round(self.origin_stock, 3),
            "origin_dos":       round(self.origin_dos, 1),
            "dest_branch_id":   self.dest_branch_id,
            "dest_name":        self.dest_name,
            "dest_stock":       round(self.dest_stock, 3),
            "dest_dos":         round(self.dest_dos, 1),
            "qty_suggested":    round(self.qty_suggested, 3),
            "urgency_score":    round(self.urgency_score, 1),
            "reason":           self.reason,
            "cv":               round(self.cv, 3),
        }


# ── Motor principal ────────────────────────────────────────────────────────────

class TransferSuggestionEngine:
    """
    Analiza stock y ventas de TODAS las sucursales activas y genera
    sugerencias de transferencia basadas en Días de Suministro (DOS)
    y Coeficiente de Variación (CV) entre sucursales.
    """

    def __init__(
        self,
        db,
        window_days:     int   = DEFAULT_WINDOW_DAYS,
        dos_min:         float = DEFAULT_DOS_MIN,
        dos_target_mult: float = DEFAULT_DOS_TARGET_MULT,
        cv_threshold:    float = DEFAULT_CV_THRESHOLD,
        min_qty:         float = DEFAULT_MIN_QTY_KG,
        min_score:       float = DEFAULT_MIN_SCORE,
    ):
        self.db             = db
        self.window_days    = window_days
        self.dos_min        = dos_min
        self.dos_target_mult = dos_target_mult
        self.cv_threshold   = cv_threshold
        self.min_qty        = min_qty
        self.min_score      = min_score

    # ── API pública ────────────────────────────────────────────────────────────

    def analyze(
        self,
        product_ids: Optional[List[int]] = None,
        branch_ids:  Optional[List[int]] = None,
        limit:       int = 50,
    ) -> List[TransferSuggestion]:
        """
        Ejecuta el análisis completo y retorna lista de sugerencias
        ordenadas por urgencia descendente.

        Args:
            product_ids: filtrar a productos específicos (None = todos activos)
            branch_ids:  filtrar a sucursales específicas (None = todas activas)
            limit:       máximo de sugerencias a retornar
        """
        branches  = self._get_branches(branch_ids)
        products  = self._get_products(product_ids)

        if len(branches) < 2:
            logger.info("Menos de 2 sucursales activas — sin sugerencias posibles.")
            return []

        suggestions: List[TransferSuggestion] = []

        for prod in products:
            pid   = prod["id"]
            pname = prod["nombre"]
            punit = prod.get("unidad", "kg")

            # Paso 1 + 2: Recopilar stock y DOS por sucursal
            infos = self._collect_branch_info(pid, branches)
            if len(infos) < 2:
                continue

            # Paso 3: Calcular CV — ¿hay desequilibrio suficiente?
            dos_values = [i.dos for i in infos if i.dos < 999]
            if len(dos_values) < 2:
                continue
            cv = self._coefficient_of_variation(dos_values)
            if cv < self.cv_threshold:
                continue  # distribución equilibrada, no hay nada que sugerir

            # Paso 4: Calcular DOS objetivo (mediana × multiplicador)
            dos_median = statistics.median(dos_values)
            dos_target = max(dos_median * self.dos_target_mult, self.dos_min * 2)

            # Clasificar sucursales en exceso/déficit
            origins  = sorted(
                [i for i in infos if i.dos > dos_target and i.stock > self.min_qty],
                key=lambda x: -x.dos  # más exceso primero
            )
            deficits = sorted(
                [i for i in infos if
                    i.dos < self._get_effective_stock_min(pid, i.branch_id) or
                    (i.dos < dos_median and i.velocity > 0)
                ],
                key=lambda x: x.dos   # más urgente primero
            )

            for dest in deficits:
                for orig in origins:
                    if orig.branch_id == dest.branch_id:
                        continue

                    # Cantidad para llevar ambos al DOS objetivo
                    excedente = (orig.dos - dos_target) * orig.velocity
                    deficit   = (dos_target - dest.dos) * max(dest.velocity, 0.01)
                    qty = max(0.0, min(excedente, deficit, orig.stock * 0.8))

                    if qty < self.min_qty:
                        continue

                    # Score de urgencia (0–100)
                    if dest.dos <= 0:
                        score = 100.0
                    else:
                        score = min(
                            100.0,
                            100.0 * max(0.0, 1.0 - dest.dos / dos_target)
                        )

                    if score < self.min_score:
                        continue

                    # Verificar si el producto está inactivo en otras sucursales
                    inactive_branches = self._get_inactive_branches(pid)
                    reason = self._build_reason(
                        orig, dest, qty, dos_target, cv, punit,
                        inactive_branches=inactive_branches
                    )

                    suggestions.append(TransferSuggestion(
                        product_id       = pid,
                        product_name     = pname,
                        product_unit     = punit,
                        origin_branch_id = orig.branch_id,
                        origin_name      = orig.branch_name,
                        origin_stock     = orig.stock,
                        origin_dos       = orig.dos,
                        dest_branch_id   = dest.branch_id,
                        dest_name        = dest.branch_name,
                        dest_stock       = dest.stock,
                        dest_dos         = dest.dos,
                        qty_suggested    = round(qty, 3),
                        urgency_score    = round(score, 1),
                        reason           = reason,
                        cv               = round(cv, 3),
                    ))

        # Ordenar por urgencia y limitar resultados
        suggestions.sort(key=lambda s: -s.urgency_score)
        return suggestions[:limit]

    # ── Consultas de datos ─────────────────────────────────────────────────────

    def _get_branches(self, branch_ids: Optional[List[int]]) -> List[Dict]:
        try:
            if branch_ids:
                placeholders = ",".join("?" * len(branch_ids))
                rows = self.db.execute(
                    f"SELECT id, nombre FROM sucursales "
                    f"WHERE activa=1 AND id IN ({placeholders}) ORDER BY id",
                    branch_ids
                ).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY id"
                ).fetchall()
            return [{"id": r[0], "nombre": r[1]} for r in rows]
        except Exception as exc:
            logger.error("_get_branches: %s", exc)
            return []

    def _get_products(self, product_ids: Optional[List[int]]) -> List[Dict]:
        """
        Retorna productos que existen en al menos DOS sucursales del análisis.
        Usa branch_products cuando existe (migración 039); fallback a productos.activo.
        Solo incluye productos activos en ≥2 sucursales — sin eso no hay transferencia posible.
        """
        try:
            # Detectar si branch_products existe
            has_bp = self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='branch_products'"
            ).fetchone() is not None
        except Exception:
            has_bp = False

        try:
            if has_bp:
                # Productos activos en al menos 2 sucursales activas (candidatos a transferencia)
                base_query = """
                    SELECT p.id, p.nombre, COALESCE(p.unidad,'kg') AS unidad
                    FROM productos p
                    WHERE p.activo = 1
                      AND p.deleted_at IS NULL
                      AND (
                          SELECT COUNT(DISTINCT bp.branch_id)
                          FROM branch_products bp
                          JOIN sucursales s ON s.id = bp.branch_id
                          WHERE bp.product_id = p.id
                            AND bp.activo      = 1
                            AND s.activa       = 1
                      ) >= 2
                """
            else:
                base_query = """
                    SELECT id, nombre, COALESCE(unidad,'kg') AS unidad
                    FROM productos
                    WHERE activo = 1
                """

            if product_ids:
                placeholders = ",".join("?" * len(product_ids))
                rows = self.db.execute(
                    f"{base_query} AND p.id IN ({placeholders}) ORDER BY p.nombre",
                    product_ids
                ).fetchall()
            else:
                rows = self.db.execute(
                    f"{base_query} ORDER BY {'p.nombre' if has_bp else 'nombre'}"
                ).fetchall()

            return [{"id": r[0], "nombre": r[1], "unidad": r[2]} for r in rows]
        except Exception as exc:
            logger.error("_get_products: %s", exc)
            return []

    def _get_stock(self, product_id: int, branch_id: int) -> float:
        """
        Lee stock actual. Prioriza inventario_actual (caché calculado),
        luego branch_inventory (batches), luego productos.existencia como fallback.
        """
        # Fuente 1: inventario_actual (más confiable post-migración 031)
        try:
            row = self.db.execute(
                "SELECT cantidad FROM inventario_actual "
                "WHERE producto_id=? AND sucursal_id=?",
                (product_id, branch_id)
            ).fetchone()
            if row and row[0] is not None:
                return max(0.0, float(row[0]))
        except Exception:
            pass

        # Fuente 2: branch_inventory (batches consolidados)
        try:
            row = self.db.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM branch_inventory "
                "WHERE product_id=? AND branch_id=?",
                (product_id, branch_id)
            ).fetchone()
            if row and row[0] is not None:
                return max(0.0, float(row[0]))
        except Exception:
            pass

        # Fuente 3: productos.existencia (single-branch fallback)
        try:
            row = self.db.execute(
                "SELECT existencia FROM productos WHERE id=?", (product_id,)
            ).fetchone()
            if row and branch_id == 1:
                return max(0.0, float(row[0] or 0))
        except Exception:
            pass

        return 0.0

    def _get_daily_sales_series(
        self, product_id: int, branch_id: int
    ) -> List[float]:
        """
        Retorna serie de ventas diarias (qty) de los últimos window_days días.
        Rellena días sin ventas con 0.
        """
        since = (date.today() - timedelta(days=self.window_days)).isoformat()
        try:
            rows = self.db.execute(
                """
                SELECT date(v.fecha) AS dia, SUM(CAST(dv.cantidad AS REAL)) AS qty
                FROM detalles_venta dv
                JOIN ventas v ON v.id = dv.venta_id
                WHERE dv.producto_id = ?
                  AND v.sucursal_id  = ?
                  AND v.estado NOT IN ('cancelada','anulada')
                  AND date(v.fecha)  >= ?
                GROUP BY date(v.fecha)
                ORDER BY dia ASC
                """,
                (product_id, branch_id, since)
            ).fetchall()
        except Exception as exc:
            logger.warning("daily_sales p=%d b=%d: %s", product_id, branch_id, exc)
            return [0.0] * self.window_days

        by_date = {r[0]: float(r[1] or 0) for r in rows}
        today   = date.today()
        return [
            by_date.get(
                (today - timedelta(days=self.window_days - i)).isoformat(), 0.0
            )
            for i in range(self.window_days)
        ]

    # ── Algoritmos matemáticos ─────────────────────────────────────────────────

    @staticmethod
    def _exp_smoothing(series: List[float], alpha: float = 0.3) -> float:
        """
        Suavizado exponencial simple.
        F_t = α × D_{t-1} + (1-α) × F_{t-1}
        Retorna estimación de demanda diaria para el siguiente período.
        """
        if not series:
            return 0.0
        alpha   = max(0.05, min(0.95, alpha))
        forecast = series[0]
        for v in series[1:]:
            forecast = alpha * v + (1 - alpha) * forecast
        return max(0.0, forecast)

    @staticmethod
    def _coefficient_of_variation(values: List[float]) -> float:
        """
        CV = σ / μ
        Mide dispersión relativa de DOS entre sucursales.
        CV > 0.40 indica distribución desequilibrada.
        Maneja casos con μ≈0 (sin ventas en ninguna sucursal).
        """
        if len(values) < 2:
            return 0.0
        finite = [v for v in values if v < 999]
        if not finite or len(finite) < 2:
            return 1.0  # todas en infinito → máximo desequilibrio
        mean_v = statistics.mean(finite)
        if mean_v < 0.001:
            return 1.0
        std_v  = statistics.stdev(finite)
        return std_v / mean_v

    @staticmethod
    def _compute_dos(stock: float, velocity: float, cap: float = 999.0) -> float:
        """
        Días de Suministro = stock / velocidad.
        Si velocidad ≈ 0 retorna `cap` (producto sin movimiento = exceso infinito).
        """
        if velocity < 0.001:
            return cap if stock > 0 else 0.0
        return min(cap, stock / velocity)

    # ── Compilación de info por sucursal ──────────────────────────────────────

    def _is_active_in_branch(self, product_id: int, branch_id: int) -> bool:
        """
        Verifica si el producto está activo en esta sucursal.
        Si branch_products no existe, asume activo (comportamiento legacy).
        """
        try:
            row = self.db.execute(
                "SELECT activo FROM branch_products WHERE product_id=? AND branch_id=?",
                (product_id, branch_id)
            ).fetchone()
            if row is None:
                return True   # No está en branch_products = no gestionado = asumir activo
            return bool(row[0])
        except Exception:
            return True       # Tabla no existe = legacy = asumir activo

    def _get_effective_stock_min(self, product_id: int, branch_id: int) -> float:
        """
        Retorna el stock mínimo efectivo: local si existe, global si no.
        Usado para ajustar dos_min dinámicamente por sucursal.
        """
        try:
            row = self.db.execute(
                "SELECT stock_min_local FROM branch_products WHERE product_id=? AND branch_id=?",
                (product_id, branch_id)
            ).fetchone()
            if row and row[0] is not None:
                velocity = self._exp_smoothing(
                    self._get_daily_sales_series(product_id, branch_id), 0.3
                )
                if velocity > 0:
                    return float(row[0]) / velocity  # convertir a días
            # Fallback: stock_minimo global del producto
            row2 = self.db.execute(
                "SELECT COALESCE(stock_minimo,5) FROM productos WHERE id=?", (product_id,)
            ).fetchone()
            return float(row2[0]) if row2 else self.dos_min
        except Exception:
            return self.dos_min

    def _collect_branch_info(
        self, product_id: int, branches: List[Dict]
    ) -> List[BranchStockInfo]:
        infos = []
        for branch in branches:
            bid   = branch["id"]
            bname = branch["nombre"]

            # Saltar si el producto está desactivado en esta sucursal
            if not self._is_active_in_branch(product_id, bid):
                continue

            stock    = self._get_stock(product_id, bid)
            series   = self._get_daily_sales_series(product_id, bid)
            velocity = self._exp_smoothing(series, alpha=0.3)
            dos      = self._compute_dos(stock, velocity)
            sales30  = sum(series)

            # Solo incluir sucursales con stock > 0 o ventas recientes
            if stock <= 0 and sales30 <= 0:
                continue

            infos.append(BranchStockInfo(
                branch_id   = bid,
                branch_name = bname,
                product_id  = product_id,
                stock       = stock,
                velocity    = velocity,
                dos         = dos,
                sales_30d   = sales30,
            ))
        return infos

    # ── Generador de explicación ───────────────────────────────────────────────

    def _get_inactive_branches(self, product_id: int) -> List[str]:
        """
        Retorna nombres de sucursales donde el producto está desactivado.
        Útil para mostrar contexto de activación en la sugerencia.
        """
        try:
            rows = self.db.execute("""
                SELECT s.nombre
                FROM sucursales s
                LEFT JOIN branch_products bp
                    ON bp.branch_id  = s.id
                   AND bp.product_id = ?
                WHERE s.activa = 1
                  AND (bp.activo = 0 OR bp.activo IS NULL)
                ORDER BY s.nombre
            """, (product_id,)).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    @staticmethod
    def _build_reason(
        orig: BranchStockInfo,
        dest: BranchStockInfo,
        qty:  float,
        dos_target: float,
        cv:   float,
        unit: str,
        inactive_branches: Optional[List[str]] = None,
    ) -> str:
        parts = []

        if orig.velocity < 0.01:
            parts.append(
                f"{orig.branch_name} tiene {orig.stock:.1f} {unit} "
                f"sin movimiento ({orig.dos:.0f}+ días de suministro)"
            )
        else:
            parts.append(
                f"{orig.branch_name} tiene exceso: "
                f"{orig.dos:.0f} días de suministro "
                f"(objetivo {dos_target:.0f} días)"
            )

        if dest.velocity < 0.01:
            parts.append(
                f"{dest.branch_name} tiene stock bajo "
                f"({dest.stock:.1f} {unit}) sin venta reciente"
            )
        elif dest.dos < 3:
            parts.append(
                f"{dest.branch_name} CRÍTICA: "
                f"solo {dest.dos:.1f} días de suministro"
            )
        else:
            parts.append(
                f"{dest.branch_name} necesita reposición: "
                f"{dest.dos:.1f} días actuales"
            )

        parts.append(
            f"CV={cv:.2f} entre sucursales (umbral 0.40). "
            f"Transferir {qty:.2f} {unit} equilibraría el sistema."
        )

        if inactive_branches:
            names = ", ".join(inactive_branches[:3])
            suffix = f" (+{len(inactive_branches)-3} más)" if len(inactive_branches) > 3 else ""
            parts.append(f"⚠️ Inactivo en: {names}{suffix}")

        return " · ".join(parts)
