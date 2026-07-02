# core/services/finance/third_party_service.py — SPJ ERP
"""
UnifiedThirdPartyService — Gestión unificada de terceros (Proveedores/Clientes).

Single Source of Truth para:
- CRUD de proveedores
- CRUD de clientes  
- Balances y saldos
- Historial de precios
- Evaluación de proveedores

Sin duplicación — toda la lógica vive aquí.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING, List, Dict, Optional, Any
from datetime import date

if TYPE_CHECKING:
    from core.services.enterprise.finance_service import FinanceService

logger = logging.getLogger("spj.third_party_service")


class UnifiedThirdPartyService:
    """Punto único de gestión para terceros (AP/AR/CRUD)."""

    def __init__(self, db_conn, finance_service: Optional["FinanceService"] = None):
        self._db = db_conn
        self._fs = finance_service

    @staticmethod
    def _to_dicts(cursor, rows) -> List[Dict[str, Any]]:
        """Convierte filas sqlite (tuplas) a lista de dicts usando cursor.description."""
        cols = [d[0] for d in (getattr(cursor, "description", None) or [])]
        if not cols:
            # Fallback defensivo: sqlite.Row ya es indexable por clave.
            if rows and hasattr(rows[0], "keys"):
                return [dict(r) for r in rows]
            return []
        return [dict(zip(cols, r)) for r in rows]

    # ══════════════════════════════════════════════════════════════════════════
    #  PROVEEDORES — CRUD
    # ══════════════════════════════════════════════════════════════════════════

    # categoria/notas/activo viven en el esquema base de proveedores (REGLA 11):
    # el servicio ya no emite DDL para garantizarlas.

    def get_proveedor(self, proveedor_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene un proveedor por ID."""
        try:
            cur = self._db.execute("""
                SELECT id, nombre, rfc, telefono, email, contacto, categoria,
                       direccion, condiciones_pago, limite_credito, banco, notas, activo
                FROM proveedores WHERE id = ?
            """, (proveedor_id,))
            row = cur.fetchone()
            if row:
                cols = [d[0] for d in (cur.description or [])]
                return dict(zip(cols, row))
        except Exception as e:
            logger.warning("get_proveedor failed: %s", e)
        return None

    def get_all_proveedores(self, activo: bool = True, limit: int = 300) -> List[Dict[str, Any]]:
        """Lista todos los proveedores (opcionalmente solo activos)."""
        try:
            sql = """
                SELECT p.id, p.nombre, p.telefono, p.email, p.contacto,
                       COALESCE(p.condiciones_pago, 0) as condiciones_pago,
                       COALESCE(SUM(ap.balance), 0) as saldo_pendiente
                FROM proveedores p
                LEFT JOIN accounts_payable ap ON ap.supplier_id = p.id AND ap.status = 'pendiente'
                WHERE p.activo = ?
                GROUP BY p.id
                ORDER BY p.nombre
                LIMIT ?
            """
            cur = self._db.execute(sql, (1 if activo else 0, limit))
            rows = cur.fetchall()
            return self._to_dicts(cur, rows)
        except Exception as e:
            logger.warning("get_all_proveedores failed: %s", e)
            return []

    def create_proveedor(self, datos: Dict[str, Any]) -> str:
        """
        Crea un nuevo proveedor.
        datos: {nombre, rfc, telefono, email, contacto, categoria, direccion,
                condiciones_pago, limite_credito, banco, notas}
        Retorna: ID UUIDv7 del nuevo proveedor
        """
        try:
            from backend.shared.ids import new_uuid as _new_uuid
            proveedor_id = _new_uuid()
            self._db.execute("""
                INSERT INTO proveedores
                (id, nombre, rfc, telefono, email, contacto, categoria,
                 direccion, condiciones_pago, limite_credito, banco, notas, activo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                proveedor_id,
                datos.get("nombre", ""),
                datos.get("rfc", ""),
                datos.get("telefono", ""),
                datos.get("email", ""),
                datos.get("contacto", ""),
                datos.get("categoria", "Productos"),
                datos.get("direccion", ""),
                int(datos.get("condiciones_pago", 0)),
                float(datos.get("limite_credito", 0)),
                datos.get("banco", ""),
                datos.get("notas", ""),
            ))
            self._db.commit()
            
            # Publicar evento
            try:
                from core.events.event_bus import get_bus
                get_bus().publish("PROVEEDOR_CREADO", {"proveedor_id": proveedor_id})
            except Exception:
                pass
            
            return proveedor_id
        except Exception as e:
            logger.error("create_proveedor failed: %s", e)
            raise

    def update_proveedor(self, proveedor_id: str, datos: Dict[str, Any]) -> bool:
        """Actualiza un proveedor existente."""
        try:
            self._db.execute("""
                UPDATE proveedores SET
                    nombre = ?, rfc = ?, telefono = ?, email = ?, contacto = ?,
                    categoria = ?, direccion = ?, condiciones_pago = ?,
                    limite_credito = ?, banco = ?, notas = ?, activo = 1
                WHERE id = ?
            """, (
                datos.get("nombre", ""),
                datos.get("rfc", ""),
                datos.get("telefono", ""),
                datos.get("email", ""),
                datos.get("contacto", ""),
                datos.get("categoria", "Productos"),
                datos.get("direccion", ""),
                int(datos.get("condiciones_pago", 0)),
                float(datos.get("limite_credito", 0)),
                datos.get("banco", ""),
                datos.get("notas", ""),
                proveedor_id,
            ))
            self._db.commit()
            
            try:
                from core.events.event_bus import get_bus
                get_bus().publish("PROVEEDOR_ACTUALIZADO", {"proveedor_id": proveedor_id})
            except Exception:
                pass
            
            return True
        except Exception as e:
            logger.error("update_proveedor failed: %s", e)
            return False

    def delete_proveedor(self, proveedor_id: int, soft: bool = True) -> bool:
        """
        Elimina un proveedor (soft delete por defecto).
        Si soft=True, marca activo=0. Si soft=False, elimina físicamente.
        """
        try:
            if soft:
                self._db.execute("UPDATE proveedores SET activo = 0 WHERE id = ?", (proveedor_id,))
            else:
                self._db.execute("DELETE FROM proveedores WHERE id = ?", (proveedor_id,))
            self._db.commit()
            
            try:
                from core.events.event_bus import get_bus
                get_bus().publish("PROVEEDOR_ELIMINADO", {"proveedor_id": proveedor_id})
            except Exception:
                pass
            
            return True
        except Exception as e:
            logger.error("delete_proveedor failed: %s", e)
            return False

    def search_proveedores(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Busca proveedores por nombre, RFC o contacto."""
        try:
            q = f"%{query}%"
            cur = self._db.execute("""
                SELECT id, nombre, telefono, email, contacto, categoria
                FROM proveedores
                WHERE activo = 1 AND (
                    nombre LIKE ? OR rfc LIKE ? OR contacto LIKE ? OR email LIKE ?
                )
                ORDER BY nombre
                LIMIT ?
            """, (q, q, q, q, limit))
            rows = cur.fetchall()
            return self._to_dicts(cur, rows)
        except Exception as e:
            logger.warning("search_proveedores failed: %s", e)
            return []

    def check_duplicate_proveedor(
        self,
        nombre: str,
        rfc: str = "",
        telefono: str = "",
        exclude_id: Optional[int] = None,
    ) -> Optional[str]:
        """
        Verifica si existe un proveedor duplicado por nombre, RFC o teléfono.

        Retorna el motivo del duplicado (str) o None si no hay duplicado.
        `exclude_id` permite excluir el propio proveedor en edición.

        Normalización: mayúsculas, sin espacios extra, solo dígitos en teléfono.
        """
        def _norm(text: str) -> str:
            return " ".join((text or "").upper().strip().split())

        def _digits(text: str) -> str:
            import re
            return re.sub(r"\D", "", str(text or ""))

        nombre_norm = _norm(nombre)
        rfc_norm    = _norm(rfc)
        tel_digits  = _digits(telefono)

        try:
            cur = self._db.execute(
                "SELECT id, nombre, rfc, telefono FROM proveedores WHERE activo=1 LIMIT 500"
            )
            rows = cur.fetchall()
            cols = [d[0] for d in (cur.description or [])]
            proveedores = [dict(zip(cols, r)) for r in rows]
        except Exception:
            return None

        for prov in proveedores:
            if exclude_id is not None and prov.get("id") == exclude_id:
                continue
            if nombre_norm and _norm(prov.get("nombre", "")) == nombre_norm:
                return f"Ya existe un proveedor con el nombre '{nombre_norm}' (ID {prov.get('id')})."
            if rfc_norm and _norm(prov.get("rfc", "")) == rfc_norm:
                return f"Ya existe un proveedor con RFC '{rfc_norm}' (ID {prov.get('id')})."
            if tel_digits and len(tel_digits) >= 7:
                prov_tel = _digits(prov.get("telefono", ""))
                if prov_tel and prov_tel == tel_digits:
                    return f"Ya existe un proveedor con ese teléfono (ID {prov.get('id')})."
        return None

    # ══════════════════════════════════════════════════════════════════════════
    #  HISTORIAL DE PRECIOS POR PROVEEDOR
    # ══════════════════════════════════════════════════════════════════════════

    def get_historial_precios(self, proveedor_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        """Obtiene historial de precios comprados a un proveedor."""
        try:
            cur = self._db.execute("""
                SELECT pr.nombre AS producto, dc.precio_unitario AS precio,
                       dc.cantidad AS cantidad, c.fecha AS fecha, c.id AS compra_id
                FROM detalles_compra dc
                JOIN productos pr ON pr.id = dc.producto_id
                JOIN compras c ON c.id = dc.compra_id
                WHERE c.proveedor_id = ?
                ORDER BY c.fecha DESC
                LIMIT ?
            """, (proveedor_id, limit))
            rows = cur.fetchall()
            return self._to_dicts(cur, rows)
        except Exception as e:
            logger.warning("get_historial_precios failed: %s", e)
            return []

    # ══════════════════════════════════════════════════════════════════════════
    #  EVALUACIÓN DE PROVEEDORES
    # ══════════════════════════════════════════════════════════════════════════

    def get_evaluacion_proveedores(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Obtiene evaluación de proveedores basada en:
        - Número de compras
        - Total comprado
        - Última compra
        - Saldo pendiente
        """
        try:
            cur = self._db.execute("""
                SELECT p.nombre,
                       COUNT(c.id) AS num_compras,
                       COALESCE(SUM(c.total), 0) AS total_comprado,
                       MAX(c.fecha) AS ultima_compra,
                       COALESCE(SUM(ap.balance), 0) AS saldo_pendiente
                FROM proveedores p
                LEFT JOIN compras c ON c.proveedor_id = p.id
                LEFT JOIN accounts_payable ap ON ap.supplier_id = p.id AND ap.status = 'pendiente'
                WHERE p.activo = 1
                GROUP BY p.id
                ORDER BY total_comprado DESC
                LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
            
            result = []
            for r in rows:
                d = dict(zip([d[0] for d in (cur.description or [])], r))
                saldo = float(d.get("saldo_pendiente", 0) or 0)
                d["estado"] = "⚠️ Saldo pendiente" if saldo > 0 else "✅ Al corriente"
                d["saldo_pendiente"] = saldo
                result.append(d)
            return result
        except Exception as e:
            logger.warning("get_evaluacion_proveedores failed: %s", e)
            return []

    # ══════════════════════════════════════════════════════════════════════════
    #  BALANCES Y SALDOS (delega a FinanceService si está disponible)
    # ══════════════════════════════════════════════════════════════════════════

    def get_balance(self, third_party_id: int, tipo: str = "proveedor") -> dict:
        """
        Retorna saldo pendiente para un tercero.
        tipo='proveedor' → CXP (accounts_payable)
        tipo='cliente'   → CXC (accounts_receivable)
        """
        try:
            if tipo == "proveedor":
                rows = self._fs.cuentas_por_pagar() if self._fs else []
                filtered = [r for r in rows
                            if str(r.get("supplier_id") or r.get("proveedor_id") or "") == third_party_id]
                saldo = sum(float(r.get("balance", r.get("saldo", 0))) for r in filtered)
                return {
                    "third_party_id": third_party_id,
                    "tipo": tipo,
                    "saldo_pendiente": round(saldo, 2),
                    "facturas": len(filtered),
                }
            else:
                rows = self._fs.cuentas_por_cobrar() if self._fs else []
                filtered = [r for r in rows
                            if str(r.get("cliente_id") or "") == third_party_id]
                saldo = sum(float(r.get("balance", r.get("saldo", 0))) for r in filtered)
                return {
                    "third_party_id": third_party_id,
                    "tipo": tipo,
                    "saldo_pendiente": round(saldo, 2),
                    "facturas": len(filtered),
                }
        except Exception as e:
            logger.warning("get_balance non-fatal: %s", e)
            return {"third_party_id": third_party_id, "tipo": tipo,
                    "saldo_pendiente": 0.0, "error": str(e)}

    def apply_payment(self, data: dict) -> dict:
        """
        Aplica un pago a CXP o CXC.
        data keys:
          account_id   — int (fila AP o AR)
          monto        — float
          tipo         — 'cxp' | 'cxc'
          metodo_pago  — str (default 'efectivo')
          usuario      — str (default 'Sistema')
          notas        — str (opcional)
        """
        try:
            account_id = str(data["account_id"])
            monto      = float(data["monto"])
            tipo       = data.get("tipo", "cxp")
            metodo     = data.get("metodo_pago", "efectivo")
            usuario    = data.get("usuario", "Sistema")
            notas      = data.get("notas")

            if tipo == "cxp":
                result = self._fs.abonar_cxp(
                    ap_id=account_id, monto=monto,
                    metodo_pago=metodo, usuario=usuario, notas=notas,
                ) or {} if self._fs else {"error": "FinanceService no disponible"}
            else:
                result = self._fs.cobrar_cxc(
                    ar_id=account_id, monto=monto,
                    metodo_pago=metodo, usuario=usuario, notas=notas,
                ) or {} if self._fs else {"error": "FinanceService no disponible"}

            try:
                from core.events.event_bus import get_bus
                from core.events.domain_events import PAYMENT_RECEIVED
                get_bus().publish(PAYMENT_RECEIVED, {
                    "account_id": account_id,
                    "tipo": tipo,
                    "monto": monto,
                    "metodo_pago": metodo,
                    "nuevo_balance": result.get("nuevo_balance", 0),
                    "nuevo_status": result.get("nuevo_status", ""),
                })
            except Exception as _e:
                logger.debug("apply_payment event non-fatal: %s", _e)

            return {"ok": True, **result}

        except Exception as e:
            logger.warning("apply_payment failed: %s", e)
            return {"ok": False, "error": str(e)}
