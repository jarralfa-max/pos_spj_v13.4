# application/services/caja_application_service.py
"""
CajaApplicationService — Fuente única de verdad para operaciones de caja.

Ruta canónica: UI → CajaApplicationService → DB
"""
from __future__ import annotations
from backend.shared.ids import new_uuid

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("spj.application.caja")

# Forma de pago que se considera efectivo
_EFECTIVO_FORMAS = frozenset({"Efectivo", "efectivo", "EFECTIVO", "cash", "Cash"})


class TurnoNoEncontradoError(Exception):
    pass


class TurnoYaAbiertoError(Exception):
    pass


class TurnoCerradoError(Exception):
    pass


class CajaApplicationService:
    """
    Orquesta operaciones de caja: turnos, movimientos, corte Z.
    Depende de: db, finance_service (para asientos contables y registrar_movimiento_manual).
    """

    def __init__(self, db, finance_service=None, caja_repo=None):
        self.db = db
        self._finance = finance_service
        self._caja_repo = caja_repo

    def _get_bus(self):
        try:
            from core.events.event_bus import get_bus
            return get_bus()
        except Exception:
            return None

    def _publish(self, event_type: str, payload: dict) -> None:
        bus = self._get_bus()
        if bus:
            try:
                bus.publish(event_type, payload)
            except Exception as e:
                logger.debug("event publish %s: %s", event_type, e)

    # ── Estado ────────────────────────────────────────────────────────────────

    def get_estado_turno(self, sucursal_id: int, usuario: str) -> Optional[Dict]:
        """Retorna el turno abierto actual o None."""
        try:
            row = self.db.execute(
                """SELECT id, fondo_inicial, fecha_apertura, cajero
                   FROM turnos_caja
                   WHERE sucursal_id=? AND cajero=? AND estado='abierto'
                   ORDER BY fecha_apertura DESC LIMIT 1""",
                (sucursal_id, usuario),
            ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.warning("get_estado_turno: %s", e)
            return None

    # ── Abrir turno ───────────────────────────────────────────────────────────

    def abrir_turno(self, sucursal_id: int, usuario: str, fondo_inicial: float) -> str:
        """Abre un nuevo turno. Lanza TurnoYaAbiertoError si ya hay uno abierto.

        REGLA CERO: identidad UUIDv7 acuñada con new_uuid() e insertada
        explícitamente en turnos_caja.id — sin rowid implícito."""
        existing = self.get_estado_turno(sucursal_id, usuario)
        if existing:
            raise TurnoYaAbiertoError("Ya hay un turno abierto para este cajero.")

        turno_id = new_uuid()
        self.db.execute(
            """INSERT INTO turnos_caja
               (id, sucursal_id, cajero, usuario, fondo_inicial, estado, fecha_apertura)
               VALUES (?,?,?,?,?,'abierto', datetime('now'))""",
            (turno_id, sucursal_id, usuario, usuario, fondo_inicial),
        )
        try:
            self.db.commit()
        except Exception:
            pass
        logger.info("Turno abierto id=%s cajero=%s fondo=%.2f", turno_id, usuario, fondo_inicial)

        self._publish("CAJA_TURNO_ABIERTO", {
            "turno_id": turno_id,
            "sucursal_id": sucursal_id,
            "usuario": usuario,
            "fondo_inicial": fondo_inicial,
        })
        return turno_id

    # ── Movimientos manuales ──────────────────────────────────────────────────

    def registrar_movimiento_manual(
        self,
        turno_id: str,
        sucursal_id: str,
        usuario: str,
        tipo: str,
        monto: float,
        concepto: str,
        modulo: str = "caja",
        referencia_tipo: str = "",
    ) -> None:
        """Registra INGRESO o RETIRO manual en el turno activo.

        Guarda: Caja/POS solo maneja dinero físico operativo de sucursal.
        Las compras de inventario y pagos a proveedores NO pasan por Caja.
        """
        if monto <= 0:
            raise ValueError("El monto debe ser mayor a cero.")
        if tipo not in ("INGRESO", "RETIRO"):
            raise ValueError(f"Tipo inválido: {tipo}. Use INGRESO o RETIRO.")
        if str(modulo or "").strip().lower() == "compras" or \
           str(referencia_tipo or "").strip().lower() == "compra":
            raise ValueError(
                "Las compras no se registran desde Caja. Use Tesorería/Capital o CxP."
            )

        self.db.execute(
            """INSERT INTO movimientos_caja
               (id, turno_id, sucursal_id, tipo, monto, concepto, usuario, fecha)
               VALUES (?,?,?,?,?,?,?, datetime('now'))""",
            (new_uuid(), turno_id, sucursal_id, tipo, monto, concepto, usuario),
        )
        try:
            self.db.commit()
        except Exception:
            pass

        self._publish("CAJA_MOVIMIENTO", {
            "turno_id": turno_id,
            "sucursal_id": sucursal_id,
            "usuario": usuario,
            "tipo": tipo,
            "monto": monto,
            "concepto": concepto,
        })

    # ── Movimientos del turno ─────────────────────────────────────────────────

    def get_movimientos_turno(self, turno_id: int, rol: str = "cajero") -> List[Dict]:
        """Retorna movimientos del turno. Filtra montos si es cajero."""
        try:
            rows = self.db.execute(
                """SELECT fecha, tipo,
                          COALESCE(concepto, descripcion, '') AS concepto,
                          monto, COALESCE(usuario,'Sistema') AS usuario,
                          turno_id
                   FROM movimientos_caja
                   WHERE turno_id=?
                   ORDER BY fecha DESC""",
                (turno_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_movimientos_turno: %s", e)
            return []

    # ── KPIs para barra de estado ─────────────────────────────────────────────

    def get_caja_kpis(self, sucursal_id: int, usuario: str) -> Dict:
        """Retorna datos para la barra de KPIs de caja."""
        kpis = {
            "fondo_inicial": 0.0,
            "total_ventas_turno": 0.0,
            "total_efectivo_turno": 0.0,
            "num_movimientos_hoy": 0,
            "num_cortes_hoy": 0,
        }
        try:
            turno = self.get_estado_turno(sucursal_id, usuario)
            if turno:
                kpis["fondo_inicial"] = float(turno.get("fondo_inicial", 0) or 0)
                formas_ef = list(_EFECTIVO_FORMAS)
                ph = ",".join("?" * len(formas_ef))
                # No filtra por usuario ni turno_id — ningún INSERT de ventas los setea.
                # Usa solo sucursal_id + fecha >= fecha_apertura (mismo criterio que corte Z).
                row_v = self.db.execute(
                    f"""SELECT
                          COALESCE(SUM(total), 0),
                          COALESCE(SUM(CASE WHEN COALESCE(forma_pago,'Efectivo') IN ({ph})
                                           THEN total ELSE 0 END), 0)
                        FROM ventas
                        WHERE sucursal_id=? AND estado='completada'
                          AND fecha >= (SELECT fecha_apertura
                                        FROM turnos_caja WHERE id=?)""",
                    tuple(formas_ef) + (sucursal_id, turno["id"]),
                ).fetchone()
                kpis["total_ventas_turno"]   = float(row_v[0] or 0) if row_v else 0.0
                kpis["total_efectivo_turno"] = float(row_v[1] or 0) if row_v else 0.0
        except Exception as e:
            logger.warning("kpis ventas: %s", e)
        try:
            row_m = self.db.execute(
                "SELECT COUNT(*) FROM movimientos_caja WHERE DATE(fecha)=DATE('now') AND sucursal_id=?",
                (sucursal_id,),
            ).fetchone()
            kpis["num_movimientos_hoy"] = int(row_m[0] or 0) if row_m else 0
        except Exception as e:
            logger.debug("kpis movs: %s", e)
        try:
            row_c = self.db.execute(
                "SELECT COUNT(*) FROM cierres_caja WHERE DATE(fecha_cierre)=DATE('now') AND sucursal_id=?",
                (sucursal_id,),
            ).fetchone()
            kpis["num_cortes_hoy"] = int(row_c[0] or 0) if row_c else 0
        except Exception as e:
            logger.debug("kpis cortes: %s", e)
        return kpis

    # ── Historial de cortes ───────────────────────────────────────────────────

    def get_historial_cortes(self, sucursal_id: int, limit: int = 100) -> List[Dict]:
        """Retorna historial de cortes Z de la sucursal."""
        try:
            rows = self.db.execute(
                """SELECT tipo, fecha_cierre, usuario, total_ventas,
                          total_efectivo, id, diferencia, fondo_inicial,
                          efectivo_contado, comentarios
                   FROM cierres_caja
                   WHERE sucursal_id=?
                   ORDER BY fecha_cierre DESC LIMIT ?""",
                (sucursal_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_historial_cortes: %s", e)
            return []

    def get_cierre_por_id(self, cierre_id: str) -> Optional[Dict]:
        """Retorna un cierre por su ID para reimpresión."""
        try:
            row = self.db.execute(
                "SELECT * FROM cierres_caja WHERE id=?", (cierre_id,)
            ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.warning("get_cierre_por_id: %s", e)
            return None

    # ── Arqueo ────────────────────────────────────────────────────────────────

    def calcular_arqueo(self, turno_id: int, total_fisico: float) -> Dict:
        """
        Calcula diferencia entre efectivo físico contado y efectivo esperado del turno.
        Solo cuenta ventas en EFECTIVO (no tarjeta ni transferencia).
        """
        try:
            row_t = self.db.execute(
                "SELECT fondo_inicial, fecha_apertura, sucursal_id, cajero FROM turnos_caja WHERE id=?",
                (turno_id,),
            ).fetchone()
            if not row_t:
                return {"error": "Turno no encontrado"}
            fondo = float(row_t["fondo_inicial"] or 0)
            fecha_apertura = row_t["fecha_apertura"]
            sucursal_id = row_t["sucursal_id"]
            cajero = row_t["cajero"]

            ventas_ef = self._sum_ventas_efectivo(sucursal_id, cajero, fecha_apertura, turno_id)
            row_m = self.db.execute(
                """SELECT
                     COALESCE(SUM(CASE WHEN tipo='INGRESO' THEN monto ELSE 0 END),0) AS ingresos,
                     COALESCE(SUM(CASE WHEN tipo='RETIRO'  THEN monto ELSE 0 END),0) AS retiros
                   FROM movimientos_caja WHERE turno_id=?""",
                (turno_id,),
            ).fetchone()
            ingresos = float(row_m["ingresos"] or 0) if row_m else 0.0
            retiros = float(row_m["retiros"] or 0) if row_m else 0.0

            esperado = fondo + ventas_ef + ingresos - retiros
            diferencia = total_fisico - esperado
            return {
                "fondo_inicial": fondo,
                "ventas_efectivo": ventas_ef,
                "ingresos": ingresos,
                "retiros": retiros,
                "esperado": esperado,
                "total_fisico": total_fisico,
                "diferencia": diferencia,
            }
        except Exception as e:
            logger.warning("calcular_arqueo: %s", e)
            return {"error": str(e)}

    def _sum_ventas_efectivo(
        self, sucursal_id: int, cajero: str, fecha_apertura: str, turno_id: int
    ) -> float:
        """Suma SOLO las ventas en efectivo del turno."""
        formas = list(_EFECTIVO_FORMAS)
        placeholders = ",".join("?" * len(formas))
        try:
            row = self.db.execute(
                f"""SELECT COALESCE(SUM(total), 0)
                    FROM ventas
                    WHERE sucursal_id=? AND estado='completada'
                      AND fecha >= ?
                      AND COALESCE(forma_pago,'Efectivo') IN ({placeholders})""",
                (sucursal_id, fecha_apertura) + tuple(formas),
            ).fetchone()
            return float(row[0] or 0) if row else 0.0
        except Exception as e:
            logger.debug("_sum_ventas_efectivo: %s", e)
            return 0.0

    def _sum_ventas_por_forma(
        self, sucursal_id: int, fecha_apertura: str, turno_id: int
    ) -> Dict:
        """Retorna breakdown de ventas por forma de pago."""
        result = {}
        try:
            rows = self.db.execute(
                """SELECT COALESCE(forma_pago,'Efectivo') AS fp,
                          COALESCE(SUM(total),0) AS total_fp,
                          COUNT(*) AS num_ventas
                   FROM ventas
                   WHERE sucursal_id=? AND estado='completada'
                     AND fecha >= (SELECT COALESCE(fecha_apertura, DATE('now'))
                                   FROM turnos_caja WHERE id=?)
                   GROUP BY fp
                   ORDER BY total_fp DESC""",
                (sucursal_id, turno_id),
            ).fetchall()
            for r in rows:
                result[r[0]] = {"total": float(r[1] or 0), "count": int(r[2] or 0)}
        except Exception as e:
            logger.debug("_sum_ventas_por_forma: %s", e)
        return result

    # ── Corte Z ───────────────────────────────────────────────────────────────

    def generar_corte_z(
        self,
        turno_id: int,
        sucursal_id: int,
        usuario: str,
        efectivo_fisico: float,
        observaciones: str = "",
    ) -> Dict:
        """
        Ejecuta el cierre Z del turno.

        Reglas de cálculo (CLAUDE.md §10):
          efectivo_esperado = fondo_inicial
                            + ventas_en_efectivo        (NO tarjeta ni transferencia)
                            + ingresos_manuales
                            - retiros
          diferencia = efectivo_fisico - efectivo_esperado
        """
        # 1. Validar turno
        row_t = self.db.execute(
            "SELECT id, estado, sucursal_id, cajero, fondo_inicial, fecha_apertura FROM turnos_caja WHERE id=?",
            (turno_id,),
        ).fetchone()
        if not row_t:
            raise TurnoNoEncontradoError(f"Turno {turno_id} no encontrado.")
        if row_t["estado"] != "abierto":
            raise TurnoCerradoError(f"El turno {turno_id} ya fue cerrado.")

        fondo = float(row_t["fondo_inicial"] or 0)
        fecha_apertura = row_t["fecha_apertura"]
        cajero = row_t["cajero"] or usuario

        # 2. Calcular ventas por forma de pago
        ventas_por_pago = self._sum_ventas_por_forma(sucursal_id, fecha_apertura, turno_id)
        total_ventas = sum(v["total"] for v in ventas_por_pago.values())
        num_ventas = sum(v["count"] for v in ventas_por_pago.values())

        # 3. Ventas solo en efectivo
        ventas_efectivo = sum(
            v["total"] for fp, v in ventas_por_pago.items()
            if fp in _EFECTIVO_FORMAS
        )

        # 4. Movimientos manuales
        row_m = self.db.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN tipo='INGRESO' THEN monto ELSE 0 END),0) AS ingresos,
                 COALESCE(SUM(CASE WHEN tipo='RETIRO'  THEN monto ELSE 0 END),0) AS retiros
               FROM movimientos_caja WHERE turno_id=?""",
            (turno_id,),
        ).fetchone()
        ingresos = float(row_m["ingresos"] or 0) if row_m else 0.0
        retiros = float(row_m["retiros"] or 0) if row_m else 0.0

        # 5. Totales por tipo de pago
        total_efectivo = ventas_efectivo
        total_tarjeta = sum(
            v["total"] for fp, v in ventas_por_pago.items()
            if "tarjeta" in fp.lower() or "card" in fp.lower()
        )
        total_transferencia = sum(
            v["total"] for fp, v in ventas_por_pago.items()
            if "transfer" in fp.lower()
        )
        total_otros = total_ventas - total_efectivo - total_tarjeta - total_transferencia

        # 6. Cálculo correcto de efectivo esperado
        esperado = round(fondo + ventas_efectivo + ingresos - retiros, 2)
        diferencia = round(efectivo_fisico - esperado, 2)

        cierre_uuid = new_uuid()
        fecha_cierre = datetime.now().isoformat()

        # 7. Transacción atómica
        sp = f"sp_corte_{new_uuid().replace('-', '')[:6]}"
        try:
            self.db.execute(f"SAVEPOINT {sp}")

            # 7a. Insertar en cierres_caja (turno_id added by migration 080)
            self.db.execute(
                """INSERT INTO cierres_caja
                   (id, uuid, tipo, sucursal_id, usuario, turno, turno_id,
                    fecha_apertura, fecha_cierre,
                    total_ventas, num_ventas,
                    total_efectivo, total_tarjeta, total_transferencia, total_otros,
                    efectivo_contado, fondo_inicial, diferencia, comentarios, estado)
                   VALUES (?,?,?,?,?,?,?,?,datetime('now'),?,?,?,?,?,?,?,?,?,?,'cerrado')""",
                (
                    cierre_uuid, cierre_uuid, "Z", sucursal_id, usuario, cajero, turno_id,
                    fecha_apertura,
                    round(total_ventas, 2), num_ventas,
                    round(total_efectivo, 2), round(total_tarjeta, 2),
                    round(total_transferencia, 2), round(max(total_otros, 0), 2),
                    round(efectivo_fisico, 2), round(fondo, 2),
                    diferencia, observaciones or "",
                ),
            )
            cierre_id = cierre_uuid  # REGLA CERO: identidad UUIDv7, sin rowid implícito

            # 7b. Actualizar turnos_caja
            self.db.execute(
                """UPDATE turnos_caja SET
                   estado='cerrado', fecha_cierre=datetime('now'),
                   total_ventas=?, efectivo_esperado=?,
                   efectivo_contado=?, diferencia=?
                   WHERE id=?""",
                (round(total_ventas, 2), esperado, efectivo_fisico, diferencia, turno_id),
            )
            self.db.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            try:
                self.db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            except Exception:
                pass
            raise

        try:
            self.db.commit()
        except Exception:
            pass

        # 8. Asiento contable si hay diferencia
        if abs(diferencia) >= 0.01 and self._finance and hasattr(self._finance, "registrar_asiento"):
            try:
                if diferencia > 0:
                    debe, haber = "110-caja", "999-diferencias-caja"
                else:
                    debe, haber = "999-diferencias-caja", "110-caja"
                self._finance.registrar_asiento(
                    debe=debe, haber=haber,
                    concepto=f"Diferencia Corte Z #{cierre_id} — cajero: {usuario}",
                    monto=abs(diferencia),
                    modulo="caja",
                    referencia_id=cierre_id,
                    sucursal_id=sucursal_id,
                    evento="CORTE_Z",
                    metadata={
                        "efectivo_contado": efectivo_fisico,
                        "efectivo_esperado": esperado,
                        "cajero": usuario,
                    },
                )
                try:
                    self.db.commit()
                except Exception:
                    pass
            except Exception as e:
                logger.warning("Corte Z asiento diferencia: %s", e)

        resultado = {
            "cierre_id": cierre_id,
            "turno_id": turno_id,
            "fondo_inicial": fondo,
            "total_ventas": round(total_ventas, 2),
            "ventas_efectivo": round(ventas_efectivo, 2),
            "otros_ingresos": round(ingresos, 2),
            "retiros": round(retiros, 2),
            "efectivo_esperado": esperado,
            "efectivo_contado": efectivo_fisico,
            "diferencia": diferencia,
            "ventas_por_pago": ventas_por_pago,
            # alias keys for UI compat
            "esperado": esperado,
            "contado": efectivo_fisico,
            "ventas_totales": round(total_ventas, 2),
        }

        # 9. Publicar eventos de dominio
        self._publish("CAJA_CORTE_Z_GENERADO", {
            "cierre_id": cierre_id,
            "turno_id": turno_id,
            "sucursal_id": sucursal_id,
            "usuario": usuario,
            "total_ventas": resultado["total_ventas"],
            "diferencia": diferencia,
        })
        if abs(diferencia) >= 0.01:
            self._publish("CAJA_DIFERENCIA_DETECTADA", {
                "cierre_id": cierre_id,
                "turno_id": turno_id,
                "sucursal_id": sucursal_id,
                "usuario": usuario,
                "diferencia": diferencia,
                "esperado": esperado,
                "contado": efectivo_fisico,
            })
        self._publish("CAJA_TURNO_CERRADO", {
            "turno_id": turno_id,
            "sucursal_id": sucursal_id,
            "usuario": usuario,
            "cierre_id": cierre_id,
        })

        logger.info(
            "Corte Z generado #%d — ventas=%d total=%.2f diff=%.2f",
            cierre_id, num_ventas, total_ventas, diferencia,
        )
        return resultado
