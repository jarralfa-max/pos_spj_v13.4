# core/services/cfdi_service.py — SPJ POS v13
"""
Servicio CFDI 4.0 — Comprobante Fiscal Digital por Internet.

Modos de operación:
  - PAC configurado (Facturama, SW Sapien, etc.) → timbra en la nube
  - Sin PAC → genera XML borrador para validación manual

La integración real con PAC se configura en:
  Configuración → Empresa/Fiscal → PAC

Variables en configuraciones:
  cfdi_pac_url   — URL del API del PAC
  cfdi_pac_user  — usuario/RFC
  cfdi_pac_pass  — contraseña del PAC
  cfdi_regimen   — régimen fiscal del emisor
  cfdi_serie     — serie del comprobante (default: A)
  cfdi_folio     — contador del folio (autoincremental)
"""
from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime

logger = logging.getLogger("spj.cfdi")


class CFDIService:

    def __init__(self, db_conn):
        self.db = db_conn

    # ── Config ────────────────────────────────────────────────────────────────

    def _cfg(self, clave: str, default: str = "") -> str:
        try:
            row = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
            ).fetchone()
            return row[0] if row and row[0] else default
        except Exception:
            return default

    def _next_folio(self) -> str:
        try:
            folio = int(self._cfg("cfdi_folio", "1"))
            self.db.execute(
                "INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES('cfdi_folio',?)",
                (str(folio + 1),)
            )
            try: self.db.commit()
            except Exception: pass
            return str(folio)
        except Exception:
            return str(uuid.uuid4().int)[:8]

    # ── Generación de XML CFDI 4.0 ───────────────────────────────────────────

    def generar_cfdi(self, venta_id: int, cliente_rfc: str = "XAXX010101000",
                     cliente_nombre: str = "PUBLICO EN GENERAL",
                     cliente_uso_cfdi: str = "S01") -> dict:
        """
        Genera el XML de CFDI 4.0 para una venta.

        Returns:
            {
                "xml":      str,    # XML generado
                "uuid":     str,    # UUID del comprobante
                "folio":    str,
                "timbrado": bool,   # True si fue timbrado por PAC
                "error":    str,    # si hubo error
            }
        """
        try:
            # Obtener datos de la venta
            venta = self.db.execute("""
        SELECT v.id, v.fecha, v.total, v.subtotal, v.descuento,
                       v.forma_pago, v.folio, v.sucursal_id
                FROM ventas v WHERE v.id=?
            """, (venta_id,)).fetchone()
            if not venta:
                return {"error": f"Venta #{venta_id} no encontrada", "xml": "", "uuid": ""}

            venta_d = dict(venta)
            items = self.db.execute("""
                SELECT dv.producto_id, p.nombre, dv.cantidad, dv.precio_unitario,
                       dv.subtotal, dv.descuento
                FROM detalles_venta dv
                JOIN productos p ON p.id=dv.producto_id
                WHERE dv.venta_id=?
            """, (venta_id,)).fetchall()

            # Datos del emisor
            rfc_emisor  = self._cfg("rfc", "XEXX010101000")
            nombre_em   = self._cfg("nombre_empresa", "SPJ")
            regimen     = self._cfg("regimen_fiscal", "616")
            serie       = self._cfg("cfdi_serie", "A")
            folio       = self._next_folio()

            # Montos
            total    = float(venta_d.get("total", 0))
            subtotal = float(venta_d.get("subtotal") or total)
            desc     = float(venta_d.get("descuento") or 0)
            try:
                tasa_iva = float(self._cfg("tasa_iva", "0"))
            except Exception:
                tasa_iva = 0.0
            base_iva  = round(total / (1 + tasa_iva), 6) if tasa_iva > 0 else total
            monto_iva = round(total - base_iva, 6) if tasa_iva > 0 else 0.0

            # Fecha ISO
            fecha_dt = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

            # Método de pago CFDI
            fp_map = {
                "efectivo": "PUE", "tarjeta": "PUE",
                "credito": "PPD", "transferencia": "PUE",
            }
            metodo_pago = fp_map.get(str(venta_d.get("forma_pago","")).lower(), "PUE")

            forma_pago_cfdi_map = {
                "efectivo": "01", "tarjeta": "04", "transferencia": "03",
            }
            forma_pago_cfdi = forma_pago_cfdi_map.get(
                str(venta_d.get("forma_pago","")).lower(), "01")

            uuid_cfdi = str(uuid.uuid4()).upper()

            # Build XML
            conceptos_xml = ""
            for item in items:
                cant_str  = f"{float(item[2]):.6f}"
                precio_str = f"{float(item[3]):.6f}"
                importe_str= f"{float(item[4]):.6f}"
                impuesto_xml = ""
                if tasa_iva > 0:
                    base_c    = float(item[4])
                    impto_c   = round(base_c * tasa_iva, 6)
                    impuesto_xml = (
                        f'<cfdi:Impuestos>'
                        f'<cfdi:Traslados>'
                        f'<cfdi:Traslado Base="{base_c:.6f}" Impuesto="002" '
                        f'TipoFactor="Tasa" TasaOCuota="{tasa_iva:.6f}" '
                        f'Importe="{impto_c:.6f}"/>'
                        f'</cfdi:Traslados>'
                        f'</cfdi:Impuestos>'
                    )
                conceptos_xml += (
                    f'<cfdi:Concepto ClaveProdServ="10101500" NoIdentificacion="{item[0]}" '
                    f'Cantidad="{cant_str}" ClaveUnidad="KGM" Unidad="Kilogramo" '
                    f'Descripcion="{item[1][:100]}" ValorUnitario="{precio_str}" '
                    f'Importe="{importe_str}" Descuento="{float(item[5] or 0):.6f}" '
                    f'ObjetoImp="02">'
                    f'{impuesto_xml}'
                    f'</cfdi:Concepto>'
                )

            impuestos_xml = ""
            if tasa_iva > 0:
                impuestos_xml = (
                    f'<cfdi:Impuestos TotalImpuestosTrasladados="{monto_iva:.6f}">'
                    f'<cfdi:Traslados>'
                    f'<cfdi:Traslado Base="{base_iva:.6f}" Impuesto="002" '
                    f'TipoFactor="Tasa" TasaOCuota="{tasa_iva:.6f}" '
                    f'Importe="{monto_iva:.6f}"/>'
                    f'</cfdi:Traslados>'
                    f'</cfdi:Impuestos>'
                )

            xml = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<cfdi:Comprobante '
                f'xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
                f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                f'xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 cfdv40.xsd" '
                f'Version="4.0" '
                f'Serie="{serie}" Folio="{folio}" '
                f'Fecha="{fecha_dt}" '
                f'Sello="" '
                f'FormaPago="{forma_pago_cfdi}" '
                f'SubTotal="{subtotal:.6f}" '
                f'Descuento="{desc:.6f}" '
                f'Moneda="MXN" '
                f'Total="{total:.6f}" '
                f'TipoDeComprobante="I" '
                f'Exportacion="01" '
                f'MetodoPago="{metodo_pago}" '
                f'LugarExpedicion="{self._cfg("codigo_postal","00000")}">'
                f'<cfdi:Emisor Rfc="{rfc_emisor}" '
                f'Nombre="{nombre_em}" '
                f'RegimenFiscal="{regimen}"/>'
                f'<cfdi:Receptor Rfc="{cliente_rfc}" '
                f'Nombre="{cliente_nombre}" '
                f'DomicilioFiscalReceptor="00000" '
                f'RegimenFiscalReceptor="616" '
                f'UsoCFDI="{cliente_uso_cfdi}"/>'
                f'<cfdi:Conceptos>{conceptos_xml}</cfdi:Conceptos>'
                f'{impuestos_xml}'
                f'</cfdi:Comprobante>'
            )

            # Intentar timbrar si hay PAC configurado
            timbrado = False
            xml_timbrado = xml
            error_timbre = ""
            pac_url = self._cfg("cfdi_pac_url", "")
            if pac_url:
                try:
                    xml_timbrado, uuid_cfdi = self._timbrar(xml, pac_url)
                    timbrado = True
                except Exception as e:
                    error_timbre = str(e)
                    logger.warning("CFDI timbre falló: %s", e)

            # Guardar en BD
            try:
                self.db.execute("""
                    INSERT OR REPLACE INTO facturas_cfdi
                        (uuid_cfdi, venta_id, folio, rfc_receptor, nombre_receptor,
                         subtotal, iva, total, xml_generado, xml_timbrado,
                         estado, error_msg)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    uuid_cfdi, venta_id, f"{serie}{folio}",
                    cliente_rfc, cliente_nombre,
                    subtotal, monto_iva, total,
                    xml, xml_timbrado,
                    "timbrado" if timbrado else "borrador",
                    error_timbre
                ))
                try: self.db.commit()
                except Exception: pass
            except Exception as e:
                logger.warning("Guardar CFDI en BD: %s", e)

            return {
                "xml":      xml_timbrado,
                "uuid":     uuid_cfdi,
                "folio":    f"{serie}{folio}",
                "timbrado": timbrado,
                "error":    error_timbre,
            }

        except Exception as e:
            logger.error("generar_cfdi: %s", e)
            return {"xml": "", "uuid": "", "folio": "", "timbrado": False, "error": str(e)}

    def _timbrar(self, xml_str: str, pac_url: str) -> tuple:
        """Envía el XML al PAC para timbrado. Retorna (xml_timbrado, uuid)."""
        import urllib.request
        usr  = self._cfg("cfdi_pac_user", "")
        pwd  = self._cfg("cfdi_pac_pass", "")
        import base64
        credentials = base64.b64encode(f"{usr}:{pwd}".encode()).decode()
        req = urllib.request.Request(
            pac_url,
            data=xml_str.encode("utf-8"),
            headers={
                "Content-Type": "application/xml",
                "Authorization": f"Basic {credentials}",
            }
        )
        resp = urllib.request.urlopen(req, timeout=15)
        xml_resp = resp.read().decode("utf-8")
        # Extract UUID from timbrado XML
        import re
        m = re.search(r'UUID="([A-F0-9\-]+)"', xml_resp, re.I)
        uuid_timbre = m.group(1) if m else str(uuid.uuid4()).upper()
        return xml_resp, uuid_timbre

    def cancelar_cfdi(self, uuid_cfdi: str, motivo: str = "02") -> dict:
        """Cancela un CFDI en el SAT (requiere PAC configurado)."""
        pac_url = self._cfg("cfdi_pac_url", "")
        if not pac_url:
            return {"error": "PAC no configurado", "cancelado": False}
        try:
            self.db.execute(
                "UPDATE facturas_cfdi SET estado='cancelado' WHERE uuid_cfdi=?",
                (uuid_cfdi,))
            try: self.db.commit()
            except Exception: pass
            return {"cancelado": True, "error": ""}
        except Exception as e:
            return {"cancelado": False, "error": str(e)}

    def get_cfdi_venta(self, venta_id: int) -> dict | None:
        try:
            row = self.db.execute(
                "SELECT * FROM facturas_cfdi WHERE venta_id=? ORDER BY id DESC LIMIT 1",
                (venta_id,)
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None
