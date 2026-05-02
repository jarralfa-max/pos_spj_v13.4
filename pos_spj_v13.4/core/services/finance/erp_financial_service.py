# core/services/finance/erp_financial_service.py
# Servicio ERP financiero auditable (Issue #104)
# Implementa: documentos_financieros, pagos_cobros, ledger, auditoria
# Regla: ninguna operación crítica se borra — sólo se reversa.
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spj.erp_financial_service")


class ERPFinancialService:
    """
    Servicio central del modelo financiero ERP.
    Orquesta: terceros, documentos, pagos/cobros, ledger, auditoría.
    """

    def __init__(self, db_conn):
        self._db = db_conn

    # ─────────────────────────────────────────────────────────────────────────
    #  TERCEROS
    # ─────────────────────────────────────────────────────────────────────────

    def crear_tercero(self, nombre: str, tipo: str = "cliente", **kwargs) -> int:
        campos = ["nombre", "tipo_tercero"]
        vals = [nombre, tipo]
        for k, v in kwargs.items():
            campos.append(k)
            vals.append(v)
        sql = f"INSERT INTO terceros ({','.join(campos)}) VALUES ({','.join(['?']*len(vals))})"
        cur = self._db.execute(sql, vals)
        self._db.commit()
        tid = cur.lastrowid
        self._ledger_evento("tercero_creado", "terceros", tid, 0, usuario_id=kwargs.get("usuario_id"))
        return tid

    def get_terceros(self, tipo: Optional[str] = None, estado: str = "activo",
                     limit: int = 200) -> List[Dict]:
        where = ["estado = ?"]
        params: list = [estado]
        if tipo:
            where.append("tipo_tercero = ?")
            params.append(tipo)
        sql = (
            f"SELECT id, tipo_tercero, nombre, rfc, telefono, correo, "
            f"limite_credito, dias_credito, estado "
            f"FROM terceros WHERE {' AND '.join(where)} ORDER BY nombre LIMIT ?"
        )
        params.append(limit)
        rows = self._db.execute(sql, params).fetchall()
        cols = ["id", "tipo_tercero", "nombre", "rfc", "telefono", "correo",
                "limite_credito", "dias_credito", "estado"]
        return [dict(zip(cols, r)) for r in rows]

    def get_saldo_tercero(self, tercero_id: int) -> float:
        """Saldo pendiente total (documentos confirmados no pagados)."""
        row = self._db.execute(
            "SELECT COALESCE(SUM(saldo_pendiente),0) FROM documentos_financieros "
            "WHERE tercero_id=? AND estado NOT IN ('pagado','cancelado','reversado')",
            (tercero_id,)
        ).fetchone()
        return float(row[0]) if row else 0.0

    # ─────────────────────────────────────────────────────────────────────────
    #  CUENTAS FINANCIERAS
    # ─────────────────────────────────────────────────────────────────────────

    def get_cuentas_financieras(self, sucursal_id: int = 1) -> List[Dict]:
        rows = self._db.execute(
            "SELECT id, nombre, tipo, moneda, estado, saldo_inicial "
            "FROM cuentas_financieras WHERE sucursal_id=? AND estado='activo' ORDER BY nombre",
            (sucursal_id,)
        ).fetchall()
        cols = ["id", "nombre", "tipo", "moneda", "estado", "saldo_inicial"]
        return [dict(zip(cols, r)) for r in rows]

    def crear_cuenta_financiera(self, nombre: str, tipo: str = "caja",
                                 sucursal_id: int = 1, **kwargs) -> int:
        campos = ["nombre", "tipo", "sucursal_id"]
        vals = [nombre, tipo, sucursal_id]
        for k, v in kwargs.items():
            campos.append(k)
            vals.append(v)
        sql = f"INSERT INTO cuentas_financieras ({','.join(campos)}) VALUES ({','.join(['?']*len(vals))})"
        cur = self._db.execute(sql, vals)
        self._db.commit()
        return cur.lastrowid

    # ─────────────────────────────────────────────────────────────────────────
    #  DOCUMENTOS FINANCIEROS
    # ─────────────────────────────────────────────────────────────────────────

    def crear_documento(self, tipo: str, total: float, tercero_id: Optional[int] = None,
                        modulo_origen: str = "ventas", sucursal_id: int = 1,
                        usuario_id: Optional[int] = None, **kwargs) -> int:
        folio = self._gen_folio("DOC", tipo)
        subtotal = kwargs.pop("subtotal", total)
        impuestos = kwargs.pop("impuestos", 0.0)
        descuentos = kwargs.pop("descuentos", 0.0)
        campos = ["folio", "tipo_documento", "total", "saldo_pendiente",
                  "subtotal", "impuestos", "descuentos",
                  "modulo_origen", "sucursal_id", "estado"]
        vals: list = [folio, tipo, total, total, subtotal, impuestos, descuentos,
                      modulo_origen, sucursal_id, "borrador"]
        if tercero_id:
            campos.append("tercero_id")
            vals.append(tercero_id)
        if usuario_id:
            campos.append("usuario_id")
            vals.append(usuario_id)
        for k, v in kwargs.items():
            campos.append(k)
            vals.append(v)
        sql = f"INSERT INTO documentos_financieros ({','.join(campos)}) VALUES ({','.join(['?']*len(vals))})"
        cur = self._db.execute(sql, vals)
        self._db.commit()
        doc_id = cur.lastrowid
        self._auditoria("crear", "documentos_financieros", doc_id,
                        valor_nuevo={"folio": folio, "tipo": tipo, "total": total},
                        usuario_id=usuario_id)
        return doc_id

    def confirmar_documento(self, doc_id: int, usuario_id: Optional[int] = None) -> bool:
        doc = self._get_documento(doc_id)
        if not doc:
            return False
        if doc["estado"] not in ("borrador",):
            raise ValueError(f"No se puede confirmar documento en estado '{doc['estado']}'")
        self._db.execute(
            "UPDATE documentos_financieros SET estado='confirmado', updated_at=datetime('now') WHERE id=?",
            (doc_id,)
        )
        self._db.commit()
        self._ledger_evento(
            f"{doc['tipo_documento']}_confirmado",
            "documentos_financieros", doc_id,
            doc["total"],
            tercero_id=doc.get("tercero_id"),
            usuario_id=usuario_id,
        )
        self._auditoria("editar", "documentos_financieros", doc_id,
                        valor_anterior={"estado": "borrador"},
                        valor_nuevo={"estado": "confirmado"},
                        usuario_id=usuario_id)
        return True

    def cancelar_documento(self, doc_id: int, motivo: str = "",
                           usuario_id: Optional[int] = None) -> bool:
        doc = self._get_documento(doc_id)
        if not doc:
            return False
        if doc["estado"] in ("cancelado", "reversado"):
            return False
        self._db.execute(
            "UPDATE documentos_financieros SET estado='cancelado', updated_at=datetime('now') WHERE id=?",
            (doc_id,)
        )
        self._db.commit()
        self._ledger_evento(
            f"{doc['tipo_documento']}_cancelado",
            "documentos_financieros", doc_id,
            -doc["total"],
            tercero_id=doc.get("tercero_id"),
            usuario_id=usuario_id,
            referencia=motivo,
        )
        self._auditoria("cancelar", "documentos_financieros", doc_id,
                        valor_anterior={"estado": doc["estado"]},
                        valor_nuevo={"estado": "cancelado"},
                        motivo=motivo, usuario_id=usuario_id)
        return True

    def get_documentos(self, tipo: Optional[str] = None, estado: Optional[str] = None,
                       tercero_id: Optional[int] = None, sucursal_id: int = 1,
                       limit: int = 200) -> List[Dict]:
        where = ["sucursal_id = ?"]
        params: list = [sucursal_id]
        if tipo:
            where.append("tipo_documento = ?")
            params.append(tipo)
        if estado:
            where.append("estado = ?")
            params.append(estado)
        if tercero_id:
            where.append("tercero_id = ?")
            params.append(tercero_id)
        sql = (
            "SELECT id, folio, tipo_documento, tercero_id, tercero_tipo, "
            "modulo_origen, fecha_emision, total, saldo_pendiente, estado "
            "FROM documentos_financieros "
            f"WHERE {' AND '.join(where)} ORDER BY fecha_emision DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._db.execute(sql, params).fetchall()
        cols = ["id", "folio", "tipo_documento", "tercero_id", "tercero_tipo",
                "modulo_origen", "fecha_emision", "total", "saldo_pendiente", "estado"]
        return [dict(zip(cols, r)) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    #  PAGOS Y COBROS
    # ─────────────────────────────────────────────────────────────────────────

    def registrar_pago_cobro(self, tipo: str, monto: float, tercero_id: Optional[int] = None,
                              forma_pago: str = "efectivo", cuenta_id: Optional[int] = None,
                              sucursal_id: int = 1, usuario_id: Optional[int] = None,
                              observaciones: str = "") -> int:
        folio = self._gen_folio("PC", tipo[:3].upper())
        cur = self._db.execute(
            "INSERT INTO pagos_cobros "
            "(folio, tipo_operacion, tercero_id, monto_total, forma_pago, "
            " cuenta_financiera_id, sucursal_id, usuario_id, observaciones, estado) "
            "VALUES (?,?,?,?,?,?,?,?,?,'registrado')",
            (folio, tipo, tercero_id, monto, forma_pago, cuenta_id,
             sucursal_id, usuario_id, observaciones)
        )
        self._db.commit()
        pc_id = cur.lastrowid
        self._auditoria("crear", "pagos_cobros", pc_id,
                        valor_nuevo={"folio": folio, "tipo": tipo, "monto": monto},
                        usuario_id=usuario_id)
        return pc_id

    def aplicar_pago_a_documentos(self, pago_cobro_id: int,
                                   aplicaciones: List[Dict[str, Any]],
                                   usuario_id: Optional[int] = None) -> bool:
        """
        Aplica un pago/cobro a uno o varios documentos.
        aplicaciones: [{"doc_id": int, "monto": float}, ...]
        """
        pc = self._db.execute(
            "SELECT monto_total, estado FROM pagos_cobros WHERE id=?", (pago_cobro_id,)
        ).fetchone()
        if not pc:
            raise ValueError(f"Pago/cobro {pago_cobro_id} no encontrado")
        if pc[1] in ("cancelado", "reversado"):
            raise ValueError(f"Pago/cobro ya en estado {pc[1]}")

        for ap in aplicaciones:
            doc_id = ap["doc_id"]
            monto_ap = float(ap["monto"])
            doc = self._get_documento(doc_id)
            if not doc:
                continue
            saldo_ant = float(doc["saldo_pendiente"])
            saldo_post = max(0.0, saldo_ant - monto_ap)
            nuevo_estado = "pagado" if saldo_post == 0 else "parcial"
            self._db.execute(
                "INSERT INTO pagos_cobros_aplicaciones "
                "(pago_cobro_id, documento_financiero_id, monto_aplicado, "
                " saldo_anterior_documento, saldo_posterior_documento, usuario_id) "
                "VALUES (?,?,?,?,?,?)",
                (pago_cobro_id, doc_id, monto_ap, saldo_ant, saldo_post, usuario_id)
            )
            self._db.execute(
                "UPDATE documentos_financieros "
                "SET saldo_pendiente=?, estado=?, updated_at=datetime('now') WHERE id=?",
                (saldo_post, nuevo_estado, doc_id)
            )
            self._ledger_evento(
                "cobro_aplicado" if "cobro" in str(
                    self._db.execute(
                        "SELECT tipo_operacion FROM pagos_cobros WHERE id=?",
                        (pago_cobro_id,)
                    ).fetchone() or ("pago",)
                ) else "pago_proveedor_aplicado",
                "pagos_cobros_aplicaciones", None,
                monto_ap,
                tercero_id=doc.get("tercero_id"),
                usuario_id=usuario_id,
                referencia=f"doc:{doc_id}",
            )

        self._db.execute(
            "UPDATE pagos_cobros SET estado='aplicado', updated_at=datetime('now') WHERE id=?",
            (pago_cobro_id,)
        )
        self._db.commit()
        return True

    def get_pagos_cobros(self, tipo: Optional[str] = None, tercero_id: Optional[int] = None,
                          sucursal_id: int = 1, limit: int = 200) -> List[Dict]:
        where = ["sucursal_id = ?"]
        params: list = [sucursal_id]
        if tipo:
            where.append("tipo_operacion = ?")
            params.append(tipo)
        if tercero_id:
            where.append("tercero_id = ?")
            params.append(tercero_id)
        sql = (
            "SELECT id, folio, tipo_operacion, tercero_id, monto_total, "
            "forma_pago, fecha, estado "
            "FROM pagos_cobros "
            f"WHERE {' AND '.join(where)} ORDER BY fecha DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._db.execute(sql, params).fetchall()
        cols = ["id", "folio", "tipo_operacion", "tercero_id", "monto_total",
                "forma_pago", "fecha", "estado"]
        return [dict(zip(cols, r)) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    #  MOVIMIENTOS FINANCIEROS
    # ─────────────────────────────────────────────────────────────────────────

    def registrar_movimiento(self, tipo: str, monto: float, cuenta_id: Optional[int] = None,
                              origen_modulo: str = "", origen_id: Optional[int] = None,
                              tercero_id: Optional[int] = None, sucursal_id: int = 1,
                              usuario_id: Optional[int] = None, referencia: str = "") -> int:
        folio = self._gen_folio("MOV", tipo[:3].upper())
        cur = self._db.execute(
            "INSERT INTO movimientos_financieros "
            "(folio, tipo_movimiento, cuenta_financiera_id, monto, "
            " origen_modulo, origen_id, tercero_id, sucursal_id, usuario_id, referencia) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (folio, tipo, cuenta_id, monto, origen_modulo, origen_id,
             tercero_id, sucursal_id, usuario_id, referencia)
        )
        self._db.commit()
        return cur.lastrowid

    def get_movimientos(self, tipo: Optional[str] = None, sucursal_id: int = 1,
                         limit: int = 200) -> List[Dict]:
        where = ["sucursal_id = ?"]
        params: list = [sucursal_id]
        if tipo:
            where.append("tipo_movimiento = ?")
            params.append(tipo)
        sql = (
            "SELECT id, folio, tipo_movimiento, cuenta_financiera_id, monto, "
            "origen_modulo, fecha, estado "
            "FROM movimientos_financieros "
            f"WHERE {' AND '.join(where)} ORDER BY fecha DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._db.execute(sql, params).fetchall()
        cols = ["id", "folio", "tipo_movimiento", "cuenta_financiera_id", "monto",
                "origen_modulo", "fecha", "estado"]
        return [dict(zip(cols, r)) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    #  LEDGER FINANCIERO
    # ─────────────────────────────────────────────────────────────────────────

    def get_ledger(self, sucursal_id: int = 1, limit: int = 200,
                   tercero_id: Optional[int] = None, evento: Optional[str] = None) -> List[Dict]:
        where = ["sucursal_id = ?"]
        params: list = [sucursal_id]
        if tercero_id:
            where.append("tercero_id = ?")
            params.append(tercero_id)
        if evento:
            where.append("evento = ?")
            params.append(evento)
        sql = (
            "SELECT id, evento, entidad_tipo, entidad_id, modulo_origen, "
            "tercero_id, monto, moneda, timestamp, referencia "
            "FROM ledger_financiero "
            f"WHERE {' AND '.join(where)} ORDER BY timestamp DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._db.execute(sql, params).fetchall()
        cols = ["id", "evento", "entidad_tipo", "entidad_id", "modulo_origen",
                "tercero_id", "monto", "moneda", "timestamp", "referencia"]
        return [dict(zip(cols, r)) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    #  CONCILIACIONES
    # ─────────────────────────────────────────────────────────────────────────

    def crear_conciliacion(self, cuenta_id: int, periodo: str, saldo_sistema: float,
                            saldo_real: float, usuario_id: Optional[int] = None,
                            sucursal_id: int = 1, notas: str = "") -> int:
        diferencia = saldo_real - saldo_sistema
        estado = "conciliado" if abs(diferencia) < 0.01 else "con_diferencia"
        folio = self._gen_folio("CONCIL", periodo.replace("-", ""))
        cur = self._db.execute(
            "INSERT INTO conciliaciones_financieras "
            "(folio, cuenta_financiera_id, periodo, saldo_sistema, saldo_real, "
            " diferencia, estado, usuario_id, sucursal_id, notas) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (folio, cuenta_id, periodo, saldo_sistema, saldo_real,
             diferencia, estado, usuario_id, sucursal_id, notas)
        )
        self._db.commit()
        self._ledger_evento(
            "conciliacion_realizada", "conciliaciones_financieras", cur.lastrowid,
            diferencia, usuario_id=usuario_id,
            referencia=f"cuenta:{cuenta_id} periodo:{periodo}"
        )
        return cur.lastrowid

    def get_conciliaciones(self, sucursal_id: int = 1, limit: int = 100) -> List[Dict]:
        rows = self._db.execute(
            "SELECT id, folio, cuenta_financiera_id, periodo, saldo_sistema, "
            "saldo_real, diferencia, estado, fecha "
            "FROM conciliaciones_financieras WHERE sucursal_id=? "
            "ORDER BY fecha DESC LIMIT ?",
            (sucursal_id, limit)
        ).fetchall()
        cols = ["id", "folio", "cuenta_financiera_id", "periodo", "saldo_sistema",
                "saldo_real", "diferencia", "estado", "fecha"]
        return [dict(zip(cols, r)) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    #  CORTES DE CAJA ERP
    # ─────────────────────────────────────────────────────────────────────────

    def abrir_corte(self, saldo_inicial: float = 0, caja_id: Optional[int] = None,
                    usuario_id: Optional[int] = None, sucursal_id: int = 1) -> int:
        folio = self._gen_folio("CORTE", datetime.now().strftime("%Y%m%d"))
        cur = self._db.execute(
            "INSERT INTO cortes_caja_erp "
            "(folio, caja_id, usuario_id, sucursal_id, saldo_inicial, estado) "
            "VALUES (?,?,?,?,?,'abierto')",
            (folio, caja_id, usuario_id, sucursal_id, saldo_inicial)
        )
        self._db.commit()
        corte_id = cur.lastrowid
        self._ledger_evento("corte_caja_abierto", "cortes_caja_erp", corte_id,
                            saldo_inicial, usuario_id=usuario_id)
        return corte_id

    def cerrar_corte(self, corte_id: int, efectivo_contado: float,
                     usuario_id: Optional[int] = None) -> Dict:
        corte = self._db.execute(
            "SELECT saldo_inicial, total_ventas, total_cobros, total_pagos, total_retiros "
            "FROM cortes_caja_erp WHERE id=?", (corte_id,)
        ).fetchone()
        if not corte:
            raise ValueError(f"Corte {corte_id} no encontrado")
        efectivo_esp = (
            float(corte[0]) + float(corte[1]) + float(corte[2]) -
            float(corte[3]) - float(corte[4])
        )
        diferencia = efectivo_contado - efectivo_esp
        self._db.execute(
            "UPDATE cortes_caja_erp SET efectivo_esperado=?, efectivo_contado=?, "
            "diferencia=?, estado='cerrado', fecha_cierre=datetime('now') WHERE id=?",
            (efectivo_esp, efectivo_contado, diferencia, corte_id)
        )
        self._db.commit()
        self._ledger_evento("corte_caja_realizado", "cortes_caja_erp", corte_id,
                            efectivo_contado, usuario_id=usuario_id)
        return {"diferencia": diferencia, "efectivo_esperado": efectivo_esp,
                "efectivo_contado": efectivo_contado}

    def get_cortes(self, sucursal_id: int = 1, limit: int = 50) -> List[Dict]:
        rows = self._db.execute(
            "SELECT id, folio, fecha_apertura, fecha_cierre, saldo_inicial, "
            "total_ventas, efectivo_esperado, efectivo_contado, diferencia, estado "
            "FROM cortes_caja_erp WHERE sucursal_id=? ORDER BY fecha_apertura DESC LIMIT ?",
            (sucursal_id, limit)
        ).fetchall()
        cols = ["id", "folio", "fecha_apertura", "fecha_cierre", "saldo_inicial",
                "total_ventas", "efectivo_esperado", "efectivo_contado", "diferencia", "estado"]
        return [dict(zip(cols, r)) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    #  KPIs GLOBALES
    # ─────────────────────────────────────────────────────────────────────────

    def kpis_erp(self, sucursal_id: int = 1) -> Dict[str, Any]:
        hoy = date.today().isoformat()
        mes_inicio = hoy[:8] + "01"
        try:
            total_cxc = float(self._db.execute(
                "SELECT COALESCE(SUM(saldo_pendiente),0) FROM documentos_financieros "
                "WHERE tipo_documento='venta' AND estado IN ('confirmado','parcial') "
                "AND sucursal_id=?", (sucursal_id,)
            ).fetchone()[0])
            total_cxp = float(self._db.execute(
                "SELECT COALESCE(SUM(saldo_pendiente),0) FROM documentos_financieros "
                "WHERE tipo_documento='compra' AND estado IN ('confirmado','parcial') "
                "AND sucursal_id=?", (sucursal_id,)
            ).fetchone()[0])
            total_ingresos = float(self._db.execute(
                "SELECT COALESCE(SUM(monto),0) FROM movimientos_financieros "
                "WHERE tipo_movimiento='entrada' AND sucursal_id=? "
                "AND fecha >= ?", (sucursal_id, mes_inicio)
            ).fetchone()[0])
            total_egresos = float(self._db.execute(
                "SELECT COALESCE(SUM(monto),0) FROM movimientos_financieros "
                "WHERE tipo_movimiento='salida' AND sucursal_id=? "
                "AND fecha >= ?", (sucursal_id, mes_inicio)
            ).fetchone()[0])
            docs_vencidos = int(self._db.execute(
                "SELECT COUNT(*) FROM documentos_financieros "
                "WHERE fecha_vencimiento < ? AND estado IN ('confirmado','parcial') "
                "AND sucursal_id=?", (hoy, sucursal_id)
            ).fetchone()[0])
        except Exception as e:
            logger.warning("kpis_erp: %s", e)
            return {}
        return {
            "cxc_pendiente": total_cxc,
            "cxp_pendiente": total_cxp,
            "ingresos_mes": total_ingresos,
            "egresos_mes": total_egresos,
            "flujo_neto": total_ingresos - total_egresos,
            "documentos_vencidos": docs_vencidos,
        }

    # ─────────────────────────────────────────────────────────────────────────
    #  HELPERS PRIVADOS
    # ─────────────────────────────────────────────────────────────────────────

    def _get_documento(self, doc_id: int) -> Optional[Dict]:
        row = self._db.execute(
            "SELECT id, folio, tipo_documento, tercero_id, total, saldo_pendiente, estado "
            "FROM documentos_financieros WHERE id=?", (doc_id,)
        ).fetchone()
        if not row:
            return None
        return dict(zip(["id", "folio", "tipo_documento", "tercero_id",
                         "total", "saldo_pendiente", "estado"], row))

    def _gen_folio(self, prefix: str, suffix: str = "") -> str:
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
        return f"{prefix}-{suffix}-{ts}" if suffix else f"{prefix}-{ts}"

    def _ledger_evento(self, evento: str, entidad_tipo: str, entidad_id: Optional[int],
                       monto: float, tercero_id: Optional[int] = None,
                       usuario_id: Optional[int] = None, referencia: str = "",
                       sucursal_id: int = 1) -> None:
        try:
            self._db.execute(
                "INSERT INTO ledger_financiero "
                "(evento, entidad_tipo, entidad_id, monto, tercero_id, "
                " usuario_id, sucursal_id, referencia) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (evento, entidad_tipo, entidad_id, monto, tercero_id,
                 usuario_id, sucursal_id, referencia)
            )
            self._db.commit()
        except Exception as e:
            logger.warning("_ledger_evento: %s", e)

    def _auditoria(self, accion: str, entidad_tipo: str, entidad_id: int,
                   valor_anterior: Optional[Dict] = None, valor_nuevo: Optional[Dict] = None,
                   motivo: str = "", usuario_id: Optional[int] = None) -> None:
        try:
            self._db.execute(
                "INSERT INTO auditoria_eventos "
                "(usuario_id, accion, entidad_tipo, entidad_id, modulo, "
                " valor_anterior_json, valor_nuevo_json, motivo) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (usuario_id, accion, entidad_tipo, entidad_id, "finanzas",
                 json.dumps(valor_anterior or {}), json.dumps(valor_nuevo or {}), motivo)
            )
            self._db.commit()
        except Exception as e:
            logger.warning("_auditoria: %s", e)
