
# core/services/asset_service.py
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AssetService:
    """
    Orquestador de Activos Fijos y Mantenimiento (EAM).
    Conecta los costos de reparación directamente con la Tesorería.
    """
    def __init__(self, db_conn, treasury_service, finance_service=None):
        self.db = db_conn
        self.treasury_service = treasury_service
        self.finance_service = finance_service

    def registrar_activo(self, nombre: str, categoria: str, numero_serie: str, valor: float, vida_util: int) -> str:
        """Registra un equipo nuevo y le genera su Código Único de Etiqueta."""
        try:
            cursor = self.db.cursor()
            
            # Generamos un código temporal, lo actualizaremos con el ID real
            cursor.execute("""
                INSERT INTO activos (nombre, categoria, numero_serie, valor_adquisicion, vida_util_anios, estado, fecha_adquisicion)
                VALUES (?, ?, ?, ?, ?, 'activo', date('now'))
            """, (nombre, categoria, numero_serie, valor, vida_util))
            
            activo_id = cursor.lastrowid
            
            # Generar Código Corporativo de Etiqueta (Ej. ACT-00015)
            codigo_etiqueta = f"ACT-{str(activo_id).zfill(5)}"
            
            # Si tuviéramos un campo 'codigo' en la tabla activos, lo actualizaríamos aquí.
            # Por ahora, usamos el ID formateado visualmente en la UI, o lo guardamos en notas.
            
            self.db.commit()
            return codigo_etiqueta
            
        except Exception as e:
            self.db.rollback()
            raise RuntimeError(f"Error al registrar el activo: {e}")

    def programar_mantenimiento(self, activo_id: int, tipo: str, descripcion: str, fecha_prog: str):
        """Agenda un mantenimiento preventivo o correctivo."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO mantenimientos (activo_id, tipo, descripcion, fecha_prog, estado)
                VALUES (?, ?, ?, ?, 'pendiente')
            """, (activo_id, tipo, descripcion, fecha_prog))
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise RuntimeError(f"Error agendando mantenimiento: {e}")

    def completar_y_pagar_mantenimiento(self, mantenimiento_id: int, costo: float, tecnico: str, metodo_pago: str, usuario: str, sucursal_id: int):
        """
        Marca el mantenimiento como listo y 🚀 ENVÍA EL GASTO A LA TESORERÍA.
        """
        try:
            import uuid as _u_sp_16f78f
            sp_16f78f = f"sp_{_u_sp_16f78f.uuid4().hex[:6]}"
            self.db.execute(f"SAVEPOINT {sp_16f78f}")
            cursor = self.db.cursor()
            
            # 1. Obtener datos del mantenimiento y del activo para el concepto
            mant = cursor.execute("""
                SELECT m.descripcion, a.nombre as activo_nombre 
                FROM mantenimientos m
                JOIN activos a ON m.activo_id = a.id
                WHERE m.id = ?
            """, (mantenimiento_id,)).fetchone()
            
            # 2. Actualizar el estado a Completado
            cursor.execute("""
                UPDATE mantenimientos 
                SET estado = 'completado', costo = ?, fecha_real = date('now'), realizado_por = ?
                WHERE id = ?
            """, (costo, tecnico, mantenimiento_id))
            
            # 3. 🚀 MAGIA ENTERPRISE: Registrar el Gasto Operativo (OPEX)
            concepto = f"Mantenimiento a {mant['activo_nombre']}: {mant['descripcion']}"
            self.treasury_service.registrar_gasto_opex(
                categoria="Mantenimiento",
                concepto=concepto,
                monto=costo,
                metodo_pago=metodo_pago,
                usuario=usuario,
                sucursal_id=sucursal_id
            )
            
            self.db.execute(f"RELEASE SAVEPOINT {sp_16f78f}")
            logger.info("Mantenimiento #%s completado y pagado.", mantenimiento_id)
        except Exception as e:
            try: self.db.execute(f"ROLLBACK TO SAVEPOINT {sp_16f78f}")
            except Exception: pass
            raise RuntimeError(f"Fallo al procesar el pago del mantenimiento: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    #  Fase 3 — Depreciación mensual y capitalización de mantenimientos
    # ══════════════════════════════════════════════════════════════════════════

    def accrual_depreciacion_mensual(self, fecha_mes: str) -> dict:
        """
        Calcula y registra la depreciación mensual de todos los activos activos.
        Genera asiento contable si finance_service está disponible:
            DEBE 6105 Depreciación de Activos / HABER 1302 Depreciación Acumulada Equipo
        fecha_mes: 'YYYY-MM'
        """
        try:
            periodo = fecha_mes[:7]
            activos = self.db.execute(
                "SELECT id, nombre, valor_adquisicion, vida_util_anios "
                "FROM activos "
                "WHERE estado='activo' AND vida_util_anios > 0 "
                "  AND valor_adquisicion > 0"
            ).fetchall()

            registros = []
            for activo in activos:
                aid    = activo[0]
                nombre = activo[1]
                valor  = float(activo[2])
                vida   = int(activo[3])
                monto_mes = round(valor / (vida * 12), 2)

                prev = self.db.execute(
                    "SELECT COALESCE(SUM(monto_mes),0) "
                    "FROM depreciacion_acumulada WHERE activo_id=?", (aid,)
                ).fetchone()[0] or 0.0
                acumulado = round(float(prev) + monto_mes, 2)

                self.db.execute(
                    """INSERT INTO depreciacion_acumulada
                           (activo_id, periodo, monto_mes, acumulado)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(activo_id, periodo) DO UPDATE SET
                           monto_mes = excluded.monto_mes,
                           acumulado = excluded.acumulado""",
                    (aid, periodo, monto_mes, acumulado),
                )

                if self.finance_service and monto_mes > 0:
                    try:
                        self.finance_service.registrar_asiento(
                            concepto=f"Depreciación {periodo} — {nombre}",
                            cuenta_debe="6105",
                            cuenta_haber="1302",
                            monto=monto_mes,
                            referencia=f"DEPR-{aid}-{periodo}",
                            usuario="sistema",
                        )
                    except Exception as e_as:
                        logger.warning("asiento depr activo %s: %s", aid, e_as)

                registros.append({
                    "activo_id": aid, "nombre": nombre,
                    "periodo": periodo, "monto_mes": monto_mes,
                    "acumulado": acumulado,
                })

            self.db.commit()
            logger.info("Depreciación mensual %s: %d activos.", periodo, len(registros))
            return {"ok": True, "periodo": periodo,
                    "activos": len(registros), "detalle": registros}

        except Exception as e:
            try: self.db.rollback()
            except Exception: pass
            logger.error("accrual_depreciacion_mensual: %s", e)
            return {"ok": False, "error": str(e)}

    def capitalizar_mantenimiento(self, mant_id: int, activo_id: int) -> dict:
        """
        Reclasifica un mantenimiento completado de OPEX a CAPEX.
        Incrementa el valor de adquisición del activo y marca el registro como capex.
        """
        try:
            mant = self.db.execute(
                "SELECT m.id, m.costo, m.estado "
                "FROM mantenimientos m "
                "WHERE m.id=? AND m.estado='completado'",
                (mant_id,),
            ).fetchone()

            if not mant:
                return {"ok": False,
                        "error": "Mantenimiento no encontrado o no está completado"}

            costo = float(mant[1] or 0)
            if costo <= 0:
                return {"ok": False, "error": "El mantenimiento no tiene costo registrado"}

            # Verificar que el activo existe
            activo = self.db.execute(
                "SELECT id FROM activos WHERE id=? AND estado='activo'", (activo_id,)
            ).fetchone()
            if not activo:
                return {"ok": False, "error": f"Activo {activo_id} no encontrado"}

            self.db.execute(
                "UPDATE activos SET valor_adquisicion = valor_adquisicion + ? WHERE id=?",
                (costo, activo_id),
            )
            self.db.execute(
                "UPDATE mantenimientos SET tipo='capex' WHERE id=?", (mant_id,)
            )
            self.db.commit()
            logger.info("Mantenimiento #%s capitalizado en activo #%s ($%.2f).",
                        mant_id, activo_id, costo)
            return {"ok": True, "mant_id": mant_id, "activo_id": activo_id,
                    "monto_capitalizado": round(costo, 2)}

        except Exception as e:
            try: self.db.rollback()
            except Exception: pass
            logger.error("capitalizar_mantenimiento: %s", e)
            return {"ok": False, "error": str(e)}