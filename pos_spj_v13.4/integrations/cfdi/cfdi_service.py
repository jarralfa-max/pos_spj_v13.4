
# integrations/cfdi/cfdi_service.py — SPJ POS v9
"""
Facturación electrónica CFDI 4.0.
Arquitectura: SPJ -> CfdiService -> PacAdapter -> PAC (Finkok/SW Sapien/Stub)
              offline-first: genera XML local, timbra cuando hay internet.
"""
from __future__ import annotations
import logging, uuid, json
from datetime import datetime
from core.db.connection import get_connection, transaction

logger = logging.getLogger("spj.cfdi")

# ── Catálogos SAT mínimos ─────────────────────────────────────────────────────
FORMAS_PAGO = {"01":"Efectivo","04":"Tarjeta de crédito","28":"Tarjeta de débito",
               "03":"Transferencia","99":"Por definir"}
METODOS_PAGO = {"PUE":"Pago en una sola exhibición","PPD":"Pago en parcialidades"}
USOS_CFDI    = {"G01":"Adquisición de mercancias","G03":"Gastos en general",
                "S01":"Sin efectos fiscales","CP01":"Pagos"}
REGIMENES    = {"601":"General de Ley","612":"Personas Físicas con actividad empresarial",
                "626":"Simplificado de confianza"}

# ── XML Builder ───────────────────────────────────────────────────────────────
def _build_xml(factura: dict) -> str:
    """Genera el XML de CFDI 4.0 sin firmar (sin sellos — requiere PAC)."""
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    items_xml = ""
    for item in factura.get("items", []):
        items_xml += f"""
    <cfdi:Concepto ClaveProdServ="{item.get('clave_sat','01010101')}"
        Cantidad="{float(item['cantidad']):.6f}"
        ClaveUnidad="{item.get('unidad_sat','ACT')}"
        Descripcion="{item['nombre']}"
        ValorUnitario="{float(item['precio_unitario']):.6f}"
        Importe="{float(item['cantidad'])*float(item['precio_unitario']):.6f}"
        ObjetoImp="02">
      <cfdi:Impuestos>
        <cfdi:Traslados>
          <cfdi:Traslado Base="{float(item['cantidad'])*float(item['precio_unitario']):.6f}"
            Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000"
            Importe="{float(item['cantidad'])*float(item['precio_unitario'])*0.16:.6f}"/>
        </cfdi:Traslados>
      </cfdi:Impuestos>
    </cfdi:Concepto>"""

    subtotal = sum(float(i["cantidad"])*float(i["precio_unitario"]) for i in factura.get("items",[]))
    iva      = round(subtotal * 0.16, 2)
    total    = round(subtotal + iva, 2)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante
  xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.sat.gob.mx/cfd/4 http://www.sat.gob.mx/sitio_internet/cfd/4/cfdv40.xsd"
  Version="4.0"
  Folio="{factura.get('folio','F001')}"
  Fecha="{now}"
  Sello=""
  FormaPago="{factura.get('forma_pago_sat','01')}"
  NoCertificado=""
  Certificado=""
  SubTotal="{subtotal:.2f}"
  Moneda="MXN"
  Total="{total:.2f}"
  TipoDeComprobante="I"
  Exportacion="01"
  MetodoPago="{factura.get('metodo_pago','PUE')}"
  LugarExpedicion="{factura.get('cp_emisor','00000')}">
  <cfdi:Emisor Rfc="{factura.get('rfc_emisor','XAXX010101000')}"
    Nombre="{factura.get('nombre_emisor','EMPRESA')}"
    RegimenFiscal="{factura.get('regimen_emisor','626')}"/>
  <cfdi:Receptor Rfc="{factura.get('rfc_receptor','XAXX010101000')}"
    Nombre="{factura.get('nombre_receptor','PUBLICO EN GENERAL')}"
    DomicilioFiscalReceptor="{factura.get('cp_receptor','00000')}"
    RegimenFiscalReceptor="{factura.get('regimen_receptor','616')}"
    UsoCFDI="{factura.get('uso_cfdi','S01')}"/>
  <cfdi:Conceptos>{items_xml}
  </cfdi:Conceptos>
  <cfdi:Impuestos TotalImpuestosTrasladados="{iva:.2f}">
    <cfdi:Traslados>
      <cfdi:Traslado Base="{subtotal:.2f}" Impuesto="002"
        TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{iva:.2f}"/>
    </cfdi:Traslados>
  </cfdi:Impuestos>
</cfdi:Comprobante>"""


# ── PAC Adapters ─────────────────────────────────────────────────────────────
class PacAdapter:
    """Interfaz base para timbrado SAT."""
    def timbrar(self, xml_sin_sello: str) -> dict:
        raise NotImplementedError

    def cancelar(self, uuid_cfdi: str, motivo: str) -> dict:
        raise NotImplementedError


class StubPacAdapter(PacAdapter):
    """Adaptador de prueba — no conecta al SAT real."""
    def timbrar(self, xml: str) -> dict:
        fake_uuid = str(uuid.uuid4()).upper()
        return {
            "ok":      True,
            "uuid":    fake_uuid,
            "xml_timbrado": xml.replace('Sello=""', f'Sello="STUB_SELLO"'),
            "qr_url":  f"https://verificacfdi.facturaelectronica.sat.gob.mx/default.aspx?id={fake_uuid}",
            "error":   None,
        }
    def cancelar(self, uuid_cfdi: str, motivo: str) -> dict:
        return {"ok": True, "mensaje": f"STUB: cancelación {uuid_cfdi} aceptada"}


class FinkokPacAdapter(PacAdapter):
    """Adaptador para PAC Finkok (requiere credenciales)."""
    def __init__(self, usuario: str, password: str, sandbox: bool = True):
        self.usuario  = usuario
        self.password = password
        self.url = ("https://demo-facturacion.finkok.com/servicios/soap/stamp.wsdl"
                    if sandbox else
                    "https://facturacion.finkok.com/servicios/soap/stamp.wsdl")

    def timbrar(self, xml: str) -> dict:
        try:
            import urllib.request, base64
            import xml.etree.ElementTree as ET
            b64 = base64.b64encode(xml.encode()).decode()
            soap = f"""<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <tns:stamp xmlns:tns="http://facturacion.finkok.com/stamp">
      <tns:xml>{b64}</tns:xml>
      <tns:username>{self.usuario}</tns:username>
      <tns:password>{self.password}</tns:password>
    </tns:stamp>
  </soap:Body>
</soap:Envelope>"""
            req = urllib.request.Request(
                self.url, soap.encode(),
                {"Content-Type":"text/xml","SOAPAction":"stamp"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                root = ET.fromstring(resp.read())
                # Parse Finkok response (simplified)
                xml_timbrado = root.findtext(".//{http://facturacion.finkok.com/stamp}xml","")
                error_msg    = root.findtext(".//{http://facturacion.finkok.com/stamp}error","")
                return {"ok": bool(xml_timbrado), "xml_timbrado": xml_timbrado,
                        "error": error_msg or None}
        except Exception as e:
            return {"ok": False, "error": str(e), "xml_timbrado": None}

    def cancelar(self, uuid_cfdi: str, motivo: str) -> dict:
        return {"ok": False, "error": "Cancelación Finkok no implementada en este stub"}


# ── CfdiService ───────────────────────────────────────────────────────────────
class CfdiService:
    def __init__(self, conn=None, pac: PacAdapter = None):
        self.conn = conn or get_connection()
        self.pac  = pac or StubPacAdapter()
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS facturas_cfdi (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid_cfdi     TEXT UNIQUE,
                venta_id      INTEGER,
                folio         TEXT,
                rfc_receptor  TEXT,
                nombre_receptor TEXT,
                subtotal      DECIMAL(12,2),
                iva           DECIMAL(12,2),
                total         DECIMAL(12,2),
                xml_generado  TEXT,
                xml_timbrado  TEXT,
                estado        TEXT DEFAULT 'pendiente',
                error_msg     TEXT,
                qr_url        TEXT,
                fecha_emision DATETIME DEFAULT (datetime('now')),
                fecha_timbrado DATETIME
            );
            CREATE INDEX IF NOT EXISTS idx_cfdi_venta
                ON facturas_cfdi(venta_id);
        """)
        try: self.conn.commit()
        except Exception: pass

    def _get_config(self, clave, default=""):
        try:
            r = self.conn.execute("SELECT valor FROM configuraciones WHERE clave=?", (clave,)).fetchone()
            return r[0] if r else default
        except Exception: return default

    def generar_y_timbrar(self, venta_id: int, datos_receptor: dict) -> dict:
        """
        Genera el XML del CFDI y lo timbra via PAC.
        Si falla el timbrado, guarda en BD como 'pendiente' para reintentar.
        """
        # Obtener datos de venta
        venta = self.conn.execute("SELECT * FROM ventas WHERE id=?", (venta_id,)).fetchone()
        if not venta:
            raise ValueError(f"Venta {venta_id} no encontrada")
        venta = dict(venta)
        items = [dict(r) for r in self.conn.execute(
            "SELECT dv.*, p.nombre FROM detalles_venta dv "
            "LEFT JOIN productos p ON p.id=dv.producto_id WHERE dv.venta_id=?",
            (venta_id,)).fetchall()]

        folio_cfdi = f"F{venta_id:06d}"
        factura = {
            "folio":            folio_cfdi,
            "rfc_emisor":       self._get_config("cfdi_rfc_emisor","XAXX010101000"),
            "nombre_emisor":    self._get_config("cfdi_razon_social","MI EMPRESA"),
            "regimen_emisor":   self._get_config("cfdi_regimen","626"),
            "cp_emisor":        self._get_config("cfdi_cp","00000"),
            "rfc_receptor":     datos_receptor.get("rfc","XAXX010101000"),
            "nombre_receptor":  datos_receptor.get("nombre","PUBLICO EN GENERAL"),
            "cp_receptor":      datos_receptor.get("cp","00000"),
            "regimen_receptor": datos_receptor.get("regimen","616"),
            "uso_cfdi":         datos_receptor.get("uso_cfdi","S01"),
            "forma_pago_sat":   "01" if venta.get("forma_pago") == "Efectivo" else "04",
            "metodo_pago":      "PUE",
            "items":            items,
        }

        xml = _build_xml(factura)
        subtotal = sum(float(i.get("cantidad",1))*float(i.get("precio_unitario",0)) for i in items)
        iva      = round(subtotal*0.16,2)

        # Guardar en BD antes de timbrar (por si el PAC falla)
        with transaction(self.conn) as c:
            fid = c.execute("""INSERT INTO facturas_cfdi
                (venta_id,folio,rfc_receptor,nombre_receptor,
                 subtotal,iva,total,xml_generado,estado)
                VALUES(?,?,?,?,?,?,?,?,'pendiente')""",
                (venta_id, folio_cfdi,
                 factura["rfc_receptor"], factura["nombre_receptor"],
                 subtotal, iva, subtotal+iva, xml)).lastrowid

        # Timbrar
        try:
            result = self.pac.timbrar(xml)
            if result.get("ok"):
                self.conn.execute("""UPDATE facturas_cfdi SET
                    uuid_cfdi=?,xml_timbrado=?,estado='timbrada',
                    qr_url=?,fecha_timbrado=datetime('now')
                    WHERE id=?""",
                    (result.get("uuid"), result.get("xml_timbrado"),
                     result.get("qr_url"), fid))
                try: self.conn.commit()
                except Exception: pass
                logger.info("CFDI timbrado: %s / venta %s", result.get("uuid"), venta_id)
                return {**result, "factura_id": fid, "folio": folio_cfdi}
            else:
                self.conn.execute(
                    "UPDATE facturas_cfdi SET estado='error',error_msg=? WHERE id=?",
                    (result.get("error","Error PAC"), fid))
                try: self.conn.commit()
                except Exception: pass
                return {**result, "factura_id": fid}
        except Exception as e:
            self.conn.execute(
                "UPDATE facturas_cfdi SET estado='error',error_msg=? WHERE id=?",
                (str(e), fid))
            try: self.conn.commit()
            except Exception: pass
            logger.error("Timbrado fallido: %s", e)
            return {"ok":False,"error":str(e),"factura_id":fid}

    def reintentar_pendientes(self) -> int:
        rows = self.conn.execute(
            "SELECT id,xml_generado FROM facturas_cfdi WHERE estado IN ('pendiente','error') LIMIT 20"
        ).fetchall()
        ok = 0
        for r in rows:
            try:
                result = self.pac.timbrar(r[1])
                if result.get("ok"):
                    self.conn.execute("""UPDATE facturas_cfdi SET
                        uuid_cfdi=?,xml_timbrado=?,estado='timbrada',
                        qr_url=?,fecha_timbrado=datetime('now') WHERE id=?""",
                        (result.get("uuid"),result.get("xml_timbrado"),
                         result.get("qr_url"),r[0]))
                    ok += 1
            except Exception: pass
        try: self.conn.commit()
        except Exception: pass
        return ok

    def get_facturas(self, limit: int = 50) -> list:
        rows = self.conn.execute(
            "SELECT * FROM facturas_cfdi ORDER BY fecha_emision DESC LIMIT ?",
            (limit,)).fetchall()
        return [dict(r) for r in rows]
