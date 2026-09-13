"""Read-only BI query service for cash register (caja) metrics.

Lee el esquema CANÓNICO de Caja: `cash_ledger_entries` (movimientos) y
`cash_cuts` (cortes X/Z).

POR QUÉ ESTE ARCHIVO CAMBIÓ ENTERO
------------------------------------
Consultaba `movimientos_caja` y `cierres_caja`, que NO EXISTEN. El contexto de
Caja se reconstruyó con nombres canónicos en inglés y este servicio se quedó
apuntando a los legacy. Como `_q` traga el error y devuelve `[]`, la sección
"Caja" del tablero llevaba pintando CEROS — indistinguible de un negocio que no
movió efectivo. Lo encontró el recorrido de rutas de BI, no un fallo visible.

TRES DECISIONES QUE NO SON UN RENOMBRADO
------------------------------------------
1. INGRESO/EGRESO ya no se adivinan. El código anterior clasificaba con
   `LOWER(tipo) IN ('ingreso','entrada','deposito',...)`, una heurística sobre
   texto libre que fallaba en silencio ante cualquier valor no previsto. El
   esquema canónico tiene `direction IN ('INFLOW','OUTFLOW')` garantizado por
   CHECK: se usa la columna, no la adivinanza.

2. Sólo cuentan los cortes Z. `cash_cuts` distingue X (lectura intermedia) de
   Z (cierre final), y su propio CHECK dice que sólo Z tiene `counted_cash` y
   `difference` no nulos. Incluir los X inflaría el número de cortes y pintaría
   diferencias de $0.00 inventadas para lecturas que no contaron efectivo.

3. "Ventas" desaparece de los cortes recientes, porque no existe. `cash_cuts`
   guarda `expected_cash` —lo que DEBERÍA haber en el cajón— y eso no es la
   venta del periodo. Mapear uno al otro habría sido la misma mentira callada
   que este archivo ya tenía. Se exponen `esperado`/`contado`/`diferencia`, que
   es lo que un corte de caja realmente es.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.bi.cash")

#: Los cortes Z son los cierres; los X son lecturas intermedias. Ver decisión 2.
_CORTE_DE_CIERRE = "cut_type = 'Z'"


class BiCashQueryService:
    def __init__(self, conn):
        self._conn = conn

    def _q(self, sql, params=()):
        try:
            return self._conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.warning("BiCashQueryService: %s", e)
            return []

    def _branch(self, f, alias="") -> tuple[str, list]:
        col = f"{alias}branch_id" if alias else "branch_id"
        if f.branch_id:
            return f" AND {col} = ?", [str(f.branch_id)]
        return "", []

    def cash_totals(self, f) -> dict:
        """Ingresos y egresos de caja + número de cortes Z del periodo.

        Las reversas son asientos propios con `direction` opuesta, así que
        sumar por dirección ya las neta: no hace falta excluirlas.
        """
        wb, pb = self._branch(f)
        row = self._q(
            "SELECT COALESCE(SUM(CASE WHEN direction='INFLOW' "
            "THEN CAST(amount AS NUMERIC) ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN direction='OUTFLOW' "
            "THEN CAST(amount AS NUMERIC) ELSE 0 END),0) "
            "FROM cash_ledger_entries "
            "WHERE DATE(recorded_at) BETWEEN ? AND ?" + wb,
            [f.date_from, f.date_to] + pb)
        ingresos = float(row[0][0]) if row else 0.0
        egresos = float(row[0][1]) if row else 0.0
        cortes = self._q(
            f"SELECT COUNT(*) FROM cash_cuts WHERE {_CORTE_DE_CIERRE} "
            "AND DATE(generated_at) BETWEEN ? AND ?" + wb,
            [f.date_from, f.date_to] + pb)
        num_cortes = int(cortes[0][0]) if cortes else 0
        return {"ingresos": ingresos, "egresos": egresos,
                "saldo": ingresos - egresos, "num_cortes": num_cortes}

    def daily_behavior(self, f) -> list[tuple[str, float, float]]:
        """(día, ingresos, egresos) para graficar el comportamiento diario."""
        wb, pb = self._branch(f)
        rows = self._q(
            "SELECT DATE(recorded_at) d, "
            "COALESCE(SUM(CASE WHEN direction='INFLOW' "
            "THEN CAST(amount AS NUMERIC) ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN direction='OUTFLOW' "
            "THEN CAST(amount AS NUMERIC) ELSE 0 END),0) "
            "FROM cash_ledger_entries "
            "WHERE DATE(recorded_at) BETWEEN ? AND ?" + wb +
            " GROUP BY d ORDER BY d", [f.date_from, f.date_to] + pb)
        return [(str(r[0])[5:], float(r[1] or 0), float(r[2] or 0)) for r in rows]

    def recent_cortes(self, f, limit: int = 15) -> list[dict]:
        """Cortes Z recientes: esperado, contado y diferencia.

        `counted_cash` y `difference` son NOT NULL para Z por CHECK del propio
        esquema, así que el `COALESCE` de antes sobra: si llegara un nulo aquí
        sería un dato corrupto, no un caso normal que valga la pena disimular.
        """
        wb, pb = self._branch(f)
        rows = self._q(
            f"SELECT generated_at, expected_cash, counted_cash, difference "
            f"FROM cash_cuts WHERE {_CORTE_DE_CIERRE} "
            "AND DATE(generated_at) BETWEEN ? AND ?" + wb +
            " ORDER BY generated_at DESC LIMIT ?",
            [f.date_from, f.date_to] + pb + [limit])
        return [{"fecha": str(r[0] or "")[:16], "esperado": float(r[1] or 0),
                 "contado": float(r[2] or 0), "diferencia": float(r[3] or 0)}
                for r in rows]
