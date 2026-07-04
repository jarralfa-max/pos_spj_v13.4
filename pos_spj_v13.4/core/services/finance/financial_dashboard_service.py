# core/services/finance/financial_dashboard_service.py — SPJ ERP v13.4
"""
Servicio de KPIs financieros para el bar superior de la UI.

Evita que la capa UI ejecute SQL directo.  La UI llama a:
    dashboard_service.get_quick_kpis()  →  dict con valores listos para mostrar
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("spj.finance.dashboard")


class FinancialDashboardService:
    """
    Consultas de KPIs rápidos para la barra de resumen del módulo de Finanzas.

    Acepta un objeto `db` con método execute() (compatible con el pool de conexiones
    SQLite de SPJ) y delega opcionalmente a treasury_service para KPIs avanzados.
    """

    def __init__(self, db, treasury_service=None):
        self._db = db
        self._ts = treasury_service

    def get_quick_kpis(self, sucursal_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Retorna un dict con los 4 KPIs del bar superior de la UI de Finanzas.

        Claves:
            cxc_pendiente   float — suma de saldo_pendiente en cuentas_por_cobrar
            cxp_pendiente   float — suma de saldo_pendiente en cuentas_por_pagar
            saldo_tesoreria float — suma de saldo en cuentas_bancarias activas
            flujo_mes       float — cálculo combinado (ventas - egresos del mes)

        Siempre retorna valores aunque falten tablas (graceful degradation).
        """
        result: Dict[str, Any] = {
            "cxc_pendiente":   0.0,
            "cxp_pendiente":   0.0,
            "saldo_tesoreria": 0.0,
            "flujo_mes":       0.0,
        }

        if self._db is None:
            return result

        try:
            r = self._db.execute(
                "SELECT COALESCE(SUM(saldo_pendiente),0) FROM cuentas_por_cobrar WHERE estado='pendiente'"
            ).fetchone()
            result["cxc_pendiente"] = float(r[0] or 0)
        except Exception:
            pass

        try:
            r = self._db.execute(
                "SELECT COALESCE(SUM(saldo_pendiente),0) FROM cuentas_por_pagar WHERE estado='pendiente'"
            ).fetchone()
            result["cxp_pendiente"] = float(r[0] or 0)
        except Exception:
            pass

        try:
            r = self._db.execute(
                "SELECT COALESCE(SUM(saldo),0) FROM cuentas_bancarias WHERE activa=1"
            ).fetchone()
            result["saldo_tesoreria"] = float(r[0] or 0)
        except Exception:
            pass

        if self._ts is not None:
            try:
                kpis = self._ts.kpis_financieros()
                eg = kpis.get("egresos") or {}
                result["flujo_mes"] = float(kpis.get("ingresos", 0) or 0) - float(eg.get("total_egresos", 0) or 0)
            except Exception:
                pass

        return result

    def get_credit_info(self, cliente_id: int) -> Dict[str, Any]:
        """
        Retorna saldo actual, límite y nombre de un cliente para validar crédito.

        Claves: saldo_actual, limite_credito, nombre
        """
        default: Dict[str, Any] = {"saldo_actual": 0.0, "limite_credito": 0.0, "nombre": ""}
        if self._db is None or not cliente_id:
            return default
        try:
            row = self._db.execute(
                "SELECT COALESCE(saldo,0), COALESCE(limite_credito,0), COALESCE(nombre,'') "
                "FROM clientes WHERE id=?",
                (cliente_id,),
            ).fetchone()
            if row:
                return {
                    "saldo_actual":    float(row[0] or 0),
                    "limite_credito":  float(row[1] or 0),
                    "nombre":          str(row[2] or ""),
                }
        except Exception as exc:
            logger.warning("get_credit_info cliente_id=%s: %s", cliente_id, exc)
        return default

    def listar_clientes(self, sucursal_id: Optional[int] = None, limit: int = 500) -> list:
        """
        Lista clientes activos para autocompletar en UI.

        Retorna lista de dicts con claves: id, nombre.
        """
        if self._db is None:
            return []
        try:
            rows = self._db.execute(
                "SELECT id, nombre FROM clientes WHERE COALESCE(activo,1)=1 ORDER BY nombre LIMIT ?",
                (limit,),
            ).fetchall()
            return [{"id": r[0], "nombre": r[1]} for r in rows]
        except Exception as exc:
            logger.warning("listar_clientes: %s", exc)
            return []

    def crear_cliente(
        self,
        nombre: str,
        telefono: str = "",
        email: str = "",
        sucursal_id: int = 1,
    ) -> int:
        """
        Crea un cliente mínimo y retorna su ID.

        Lanza ValueError si el nombre está vacío.
        """
        nombre = (nombre or "").strip()
        if not nombre:
            raise ValueError("El nombre del cliente es obligatorio.")
        if self._db is None:
            raise RuntimeError("DB no disponible.")
        from backend.shared.ids import new_uuid
        cliente_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
        self._db.execute(
            "INSERT INTO clientes(id, nombre, telefono, email, activo, sucursal_id, fecha_registro) "
            "VALUES (?,?,?,?,1,?,datetime('now'))",
            (cliente_id, nombre, (telefono or "").strip(), (email or "").strip(), sucursal_id),
        )
        try:
            self._db.commit()
        except Exception:
            pass
        return cliente_id
