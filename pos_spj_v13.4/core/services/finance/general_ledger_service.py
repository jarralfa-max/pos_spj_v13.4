# core/services/finance/general_ledger_service.py — SPJ ERP v13.4
"""
GeneralLedgerService — Motor de Libro Mayor (doble entrada).

Extraído de FinanceService (FASE 5 auditoría).
FinanceService conserva métodos públicos como wrappers legacy que delegan aquí.

Responsabilidades:
  - registrar_asiento(debe, haber, monto, ...)   → financial_event_log
  - obtener_ledger(cuenta, ...)                  → filtro por cuenta/fecha
  - generar_poliza_periodo(desde, hasta, ...)    → póliza balanceada
  - exportar_poliza_periodo(...)                 → JSON o CSV

Reglas de atomicidad:
  - registrar_asiento NO hace commit: el caller es responsable.
  - Si el caller está dentro de SAVEPOINT, el asiento queda pendiente hasta RELEASE.
  - Si el caller no tiene transacción abierta, debe llamar db.commit() después.
"""
from __future__ import annotations

import csv
import json
import logging
from io import StringIO
from typing import Dict, List, Optional

logger = logging.getLogger("spj.finance.ledger")


class GeneralLedgerService:
    """Servicio canónico de libro mayor (journal entries)."""

    def __init__(self, db):
        from core.db.connection import wrap
        self._db = wrap(db)

    # ──────────────────────────────────────────────────────────────────────────
    #  REGISTRAR ASIENTO
    # ──────────────────────────────────────────────────────────────────────────

    def registrar_asiento(
        self,
        debe: str,
        haber: str,
        concepto: str,
        monto: float,
        modulo: str = "",
        referencia_id: Optional[int] = None,
        usuario_id: Optional[int] = None,
        sucursal_id: int = 1,
        evento: str = "ASIENTO_MANUAL",
        metadata: Optional[dict] = None,
    ) -> int:
        """
        Inserta un asiento de doble entrada en financial_event_log.

        Garantiza debe=haber mediante el campo único `monto`.
        NO hace commit — el caller decide cuándo confirmar la transacción.

        Returns: id del registro (0 si tabla no existe — graceful degradation).
        """
        try:
            from backend.shared.ids import new_uuid
            event_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
            self._db.execute(
                """INSERT INTO financial_event_log
                   (id, evento, modulo, referencia_id, monto, cuenta_debe, cuenta_haber,
                    usuario_id, sucursal_id, metadata)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    evento,
                    modulo or concepto,
                    referencia_id,
                    monto,
                    debe,
                    haber,
                    usuario_id,
                    sucursal_id,
                    json.dumps({"concepto": concepto, **(metadata or {})}, ensure_ascii=False),
                ),
            )
            return event_id
        except Exception as exc:
            logger.warning("registrar_asiento non-fatal: %s", exc)
            return 0

    # ──────────────────────────────────────────────────────────────────────────
    #  CONSULTAS
    # ──────────────────────────────────────────────────────────────────────────

    def obtener_ledger(
        self,
        cuenta: str,
        fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retorna asientos filtrados por cuenta (debe O haber) y rango de fechas.
        """
        params: list = [cuenta, cuenta]
        where = "(cuenta_debe=? OR cuenta_haber=?)"
        if fecha_desde:
            where += " AND timestamp >= ?"
            params.append(fecha_desde)
        if fecha_hasta:
            where += " AND timestamp <= ?"
            params.append(fecha_hasta)
        try:
            rows = self._db.execute(
                f"SELECT * FROM financial_event_log WHERE {where} ORDER BY timestamp",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def generar_poliza_periodo(
        self,
        fecha_desde: str,
        fecha_hasta: str,
        sucursal_id: Optional[int] = None,
        cuentas: Optional[List[str]] = None,
        eventos: Optional[List[str]] = None,
    ) -> Dict:
        """
        Genera póliza contable consolidada por período.

        Retorna dict con movimientos, totales debe/haber y flag `balanceado`.
        Compatible con SQLite (usa DATE(timestamp)).
        """
        where = ["DATE(timestamp) BETWEEN DATE(?) AND DATE(?)"]
        params: list = [fecha_desde, fecha_hasta]
        if sucursal_id is not None:
            where.append("sucursal_id = ?")
            params.append(sucursal_id)
        if cuentas:
            phs = ",".join("?" for _ in cuentas)
            where.append(f"(cuenta_debe IN ({phs}) OR cuenta_haber IN ({phs}))")
            params.extend(cuentas)
            params.extend(cuentas)
        if eventos:
            phs = ",".join("?" for _ in eventos)
            where.append(f"evento IN ({phs})")
            params.extend(eventos)

        try:
            rows = self._db.execute(
                f"""SELECT id, timestamp, evento, modulo, referencia_id, monto,
                          cuenta_debe, cuenta_haber, usuario_id, sucursal_id, metadata
                   FROM financial_event_log
                   WHERE {' AND '.join(where)}
                   ORDER BY timestamp, id""",
                params,
            ).fetchall()
        except Exception:
            rows = []

        movimientos = []
        total_debe = total_haber = 0.0
        for r in rows:
            d = dict(r)
            monto = float(d.get("monto") or 0.0)
            total_debe  += monto
            total_haber += monto
            movimientos.append({
                "id":           d.get("id"),
                "fecha":        d.get("timestamp"),
                "evento":       d.get("evento"),
                "modulo":       d.get("modulo"),
                "referencia_id":d.get("referencia_id"),
                "debe":         d.get("cuenta_debe"),
                "haber":        d.get("cuenta_haber"),
                "monto":        round(monto, 2),
                "sucursal_id":  d.get("sucursal_id"),
                "metadata":     d.get("metadata"),
            })

        desbalance = round(total_debe - total_haber, 4)
        return {
            "fecha_desde":  fecha_desde,
            "fecha_hasta":  fecha_hasta,
            "sucursal_id":  sucursal_id,
            "cuentas":      cuentas or [],
            "eventos":      eventos or [],
            "num_asientos": len(movimientos),
            "total_debe":   round(total_debe, 2),
            "total_haber":  round(total_haber, 2),
            "balanceado":   abs(desbalance) < 0.0001,
            "desbalance":   desbalance,
            "movimientos":  movimientos,
        }

    def exportar_poliza_periodo(
        self,
        fecha_desde: str,
        fecha_hasta: str,
        sucursal_id: Optional[int] = None,
        cuentas: Optional[List[str]] = None,
        eventos: Optional[List[str]] = None,
        formato: str = "json",
    ) -> str:
        """Exporta póliza a JSON o CSV (sin dependencias externas)."""
        poliza = self.generar_poliza_periodo(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            sucursal_id=sucursal_id,
            cuentas=cuentas,
            eventos=eventos,
        )
        fmt = (formato or "json").strip().lower()
        if fmt == "json":
            return json.dumps(poliza, ensure_ascii=False, indent=2)
        if fmt == "csv":
            out = StringIO()
            writer = csv.writer(out)
            writer.writerow([
                "id", "fecha", "evento", "modulo", "referencia_id",
                "debe", "haber", "monto", "sucursal_id", "metadata",
            ])
            for m in poliza.get("movimientos", []):
                writer.writerow([
                    m.get("id"), m.get("fecha"), m.get("evento"), m.get("modulo"),
                    m.get("referencia_id"), m.get("debe"), m.get("haber"),
                    m.get("monto"), m.get("sucursal_id"), m.get("metadata"),
                ])
            return out.getvalue()
        raise ValueError("Formato no soportado. Usa 'json' o 'csv'.")
