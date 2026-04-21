# core/services/finance/fiscal_engine.py — SPJ ERP
"""
FiscalEngine — Cálculos fiscales SAT México (IVA / ISR / Retenciones).

Consolidates scattered tax logic from cfdi_service, rrhh_service, and
template_engine into a single, stateless, zero-dependency service.

All methods are pure functions (no DB, no network). Thread-safe.
"""
from __future__ import annotations
from typing import Dict, Tuple
import logging

logger = logging.getLogger("spj.fiscal")

# SAT Art. 96 LISR 2024 — tarifa mensual (lím_inf, lím_sup, cuota_fija, tasa_marginal)
_ISR_TABLA_MENSUAL_2024: Tuple = (
    (0.01,       746.04,    0.00,    0.0192),
    (746.05,    6332.05,   14.32,    0.0640),
    (6332.06,  11128.01,  371.83,    0.1088),
    (11128.02, 12935.82,  893.63,    0.1600),
    (12935.83, 15487.71, 1182.88,    0.1792),
    (15487.72, 31236.49, 1640.18,    0.2136),
    (31236.50, 49233.00, 5004.12,    0.2352),
    (49233.01, 93993.90, 9236.89,    0.3000),
    (93993.91, 125325.20, 22665.17,  0.3200),
    (125325.21, 375975.61, 32691.18, 0.3400),
    (375975.62, float("inf"), 117912.32, 0.3500),
)

# IVA general México
IVA_GENERAL = 0.16
# IVA frontera norte (franja fronteriza)
IVA_FRONTERA = 0.08
# ISR retención a honorarios y arrendamiento (Art. 106 LISR)
ISR_RETENCION_HONORARIOS = 0.10
# IVA retención a personas físicas con actividad empresarial (2/3 del IVA)
IVA_RETENCION_PERSONAS_FISICAS = 2 / 3


class FiscalEngine:
    """
    Stateless fiscal calculator. Can be instantiated once and reused.
    Optional db_conn enables config lookups (tasa_iva from configuraciones).
    """

    def __init__(self, db_conn=None):
        self._db = db_conn
        self._tasa_iva_cache: float | None = None

    # ── IVA ─────────────────────────────────────────────────────────────────

    def tasa_iva(self) -> float:
        """Return configured IVA rate (from DB) or IVA_GENERAL default."""
        if self._tasa_iva_cache is not None:
            return self._tasa_iva_cache
        tasa = IVA_GENERAL
        if self._db:
            try:
                row = self._db.execute(
                    "SELECT valor FROM configuraciones WHERE clave='tasa_iva' LIMIT 1"
                ).fetchone()
                if row:
                    tasa = float(row[0])
            except Exception:
                pass
        self._tasa_iva_cache = tasa
        return tasa

    def desglosar_iva(self, total: float, tasa: float | None = None) -> Dict:
        """
        Separates IVA from a price-inclusive total.

        Returns: {base, iva, total, tasa_pct}
        """
        if tasa is None:
            tasa = self.tasa_iva()
        tasa = float(tasa)
        total = float(total)
        if tasa > 0:
            base = round(total / (1 + tasa), 6)
            iva  = round(total - base, 6)
        else:
            base = total
            iva  = 0.0
        return {
            "base":      base,
            "iva":       iva,
            "total":     round(base + iva, 6),
            "tasa_pct":  round(tasa * 100, 2),
        }

    def agregar_iva(self, subtotal: float, tasa: float | None = None) -> Dict:
        """
        Adds IVA on top of a tax-excluded subtotal.

        Returns: {base, iva, total, tasa_pct}
        """
        if tasa is None:
            tasa = self.tasa_iva()
        tasa    = float(tasa)
        subtotal = float(subtotal)
        iva     = round(subtotal * tasa, 6)
        return {
            "base":     subtotal,
            "iva":      iva,
            "total":    round(subtotal + iva, 6),
            "tasa_pct": round(tasa * 100, 2),
        }

    def desglose_factura(
        self,
        subtotal: float,
        iva_pct: float | None = None,
        descuento_pct: float = 0.0,
        retencion_iva: bool = False,
    ) -> Dict:
        """
        Full invoice breakdown: subtotal → descuento → base gravable → IVA → retención.

        retencion_iva=True  applies the 2/3 IVA retention rule for individual
        service providers (Art. 1-A LIVA).
        """
        if iva_pct is None:
            iva_pct = self.tasa_iva() * 100
        tasa = iva_pct / 100
        subtotal    = float(subtotal)
        descuento   = round(subtotal * float(descuento_pct) / 100, 6)
        base        = round(subtotal - descuento, 6)
        iva         = round(base * tasa, 6)
        ret_iva     = round(iva * IVA_RETENCION_PERSONAS_FISICAS, 6) if retencion_iva else 0.0
        total_pagar = round(base + iva - ret_iva, 6)
        return {
            "subtotal":       subtotal,
            "descuento":      descuento,
            "base_gravable":  base,
            "iva":            iva,
            "retencion_iva":  ret_iva,
            "total":          total_pagar,
            "tasa_pct":       round(tasa * 100, 2),
        }

    # ── ISR ─────────────────────────────────────────────────────────────────

    def calcular_isr_mensual(self, salario_mensual: float) -> Dict:
        """
        Monthly ISR withholding for employees — SAT Art. 96 LISR 2024.
        Same table as rrhh_service.calcular_isr_mensual().
        """
        salario_mensual = float(salario_mensual)
        if salario_mensual <= 0:
            return {"salario_mensual": 0.0, "isr_mensual": 0.0, "tasa_efectiva_pct": 0.0}

        isr = 0.0
        for li, ls, cuota_fija, tasa in _ISR_TABLA_MENSUAL_2024:
            if li <= salario_mensual <= ls:
                isr = cuota_fija + (salario_mensual - li) * tasa
                break

        isr = max(0.0, round(isr, 2))
        tasa_efectiva = round((isr / salario_mensual) * 100, 2) if salario_mensual > 0 else 0.0
        return {
            "salario_mensual":   round(salario_mensual, 2),
            "isr_mensual":       isr,
            "tasa_efectiva_pct": tasa_efectiva,
        }

    def calcular_isr_anual(self, ingreso_anual: float) -> Dict:
        """
        Annual ISR estimate — uses monthly table × 12 proxy.
        For formal annual returns use SAT's annual tariff table.
        """
        mensual = ingreso_anual / 12
        result  = self.calcular_isr_mensual(mensual)
        return {
            "ingreso_anual":     round(ingreso_anual, 2),
            "isr_anual":         round(result["isr_mensual"] * 12, 2),
            "tasa_efectiva_pct": result["tasa_efectiva_pct"],
        }

    def calcular_retencion_proveedor(
        self,
        monto: float,
        tipo: str = "honorarios",
    ) -> Dict:
        """
        ISR withholding for service providers (Art. 106 LISR).
        tipo: 'honorarios' (10%) | 'arrendamiento' (10%)
        Returns amounts to pay supplier and retain for SAT.
        """
        monto = float(monto)
        tasa  = ISR_RETENCION_HONORARIOS  # 10% for both types in 2024
        retencion  = round(monto * tasa, 6)
        pago_neto  = round(monto - retencion, 6)
        return {
            "monto_bruto":  monto,
            "retencion_isr": retencion,
            "pago_neto":    pago_neto,
            "tasa_pct":     round(tasa * 100, 2),
            "tipo":         tipo,
        }

    # ── Utilidades ──────────────────────────────────────────────────────────

    def periodo_fiscal(self, fecha_str: str) -> Dict:
        """
        Returns fiscal period metadata for a date string (YYYY-MM-DD).
        Useful for grouping transactions into SAT reporting periods.
        """
        from datetime import date
        try:
            d = date.fromisoformat(fecha_str[:10])
        except ValueError:
            d = date.today()
        return {
            "anio":     d.year,
            "mes":      d.month,
            "trimestre": (d.month - 1) // 3 + 1,
            "bimestre":  (d.month - 1) // 2 + 1,
            "periodo":   d.strftime("%Y-%m"),
        }

    def invalidar_cache(self) -> None:
        """Force re-read of tasa_iva from DB on next call."""
        self._tasa_iva_cache = None
