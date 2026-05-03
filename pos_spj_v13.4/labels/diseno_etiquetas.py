
# labels/diseno_etiquetas.py — SPJ POS v11
"""
Diseños de etiquetas para impresora térmica.
Genera ZPL (Zebra), TSPL (TSC) y HTML como fallback.
"""
from __future__ import annotations
from datetime import datetime


class DisenoEtiquetas:
    """Genera comandos ZPL/TSPL para impresoras térmicas de etiquetas."""

    @staticmethod
    def zpl_contenedor(datos: dict) -> str:
        """ZPL para Zebra — etiqueta contenedor proveedor 60x40mm."""
        uuid_qr   = datos.get("uuid_qr", "")
        contenido = f"SPJ:CONT:{uuid_qr}"
        nombre    = datos.get("producto", "")[:25]
        proveedor = datos.get("proveedor", "")[:25]
        lote      = datos.get("numero_lote", "")[:15]
        fecha     = datos.get("fecha_recepcion", datetime.now().strftime("%d/%m/%Y"))
        peso      = datos.get("peso_kg", "")
        return (
            "^XA\n"
            "^CI28\n"               # UTF-8
            "^FO20,10^BQN,2,4\n"   # QR
            f"^FDMA,{contenido}^FS\n"
            f"^FO160,10^A0N,18,18^FD{nombre}^FS\n"
            f"^FO160,32^A0N,14,14^FDProv: {proveedor}^FS\n"
            f"^FO160,50^A0N,14,14^FDLote: {lote}^FS\n"
            f"^FO160,66^A0N,12,12^FD{fecha} | {peso}kg^FS\n"
            f"^FO160,82^A0N,10,10^FD{uuid_qr}^FS\n"
            "^XZ\n"
        )

    @staticmethod
    def zpl_producto(datos: dict) -> str:
        """ZPL para etiqueta de producto 50x30mm."""
        uuid_qr   = datos.get("uuid_qr", "")
        contenido = f"SPJ:PROD:{uuid_qr}"
        nombre    = datos.get("nombre", "")[:25]
        precio    = float(datos.get("precio", 0))
        lote      = datos.get("lote", "")
        return (
            "^XA\n"
            "^FO10,10^BQN,2,3\n"
            f"^FDMA,{contenido}^FS\n"
            f"^FO120,10^A0N,18,18^FD{nombre}^FS\n"
            f"^FO120,30^A0N,22,22^FD${precio:.2f}/kg^FS\n"
            f"^FO120,56^A0N,12,12^FDLote: {lote}^FS\n"
            f"^FO120,70^A0N,10,10^FD{uuid_qr[:16]}^FS\n"
            "^XZ\n"
        )

    @staticmethod
    def zpl_fidelidad(datos: dict) -> str:
        """ZPL para tarjeta de fidelidad 80x50mm."""
        uuid_qr   = datos.get("uuid_qr", "")
        contenido = f"SPJ:FIDEL:{uuid_qr}"
        nombre    = datos.get("nombre_cliente", "")[:30]
        puntos    = datos.get("puntos", 0)
        return (
            "^XA\n"
            "^FO10,10^BQN,2,5\n"
            f"^FDMA,{contenido}^FS\n"
            f"^FO160,10^A0N,20,20^FDTARJETA FIDELIDAD^FS\n"
            f"^FO160,35^A0N,18,18^FD{nombre}^FS\n"
            f"^FO160,58^A0N,16,16^FDPuntos: {puntos}^FS\n"
            f"^FO160,78^A0N,12,12^FD{uuid_qr}^FS\n"
            "^XZ\n"
        )

    @staticmethod
    def tspl_contenedor(datos: dict) -> str:
        """TSPL para TSC — 60x40mm a 203dpi."""
        uuid_qr   = datos.get("uuid_qr", "")
        contenido = f"SPJ:CONT:{uuid_qr}"
        nombre    = datos.get("producto", "")[:25]
        proveedor = datos.get("proveedor", "")[:25]
        lote      = datos.get("numero_lote", "")[:15]
        fecha     = datos.get("fecha_recepcion", datetime.now().strftime("%d/%m/%Y"))
        peso      = datos.get("peso_kg", "")
        return (
            "SIZE 60 mm, 40 mm\n"
            "GAP 3 mm, 0 mm\n"
            "CLS\n"
            f'QRCODE 10,10,L,4,A,0,"{contenido}"\n'
            f'TEXT 160,10,"3",0,1,1,"{nombre}"\n'
            f'TEXT 160,30,"2",0,1,1,"Prov: {proveedor}"\n'
            f'TEXT 160,50,"2",0,1,1,"Lote: {lote}"\n'
            f'TEXT 160,68,"2",0,1,1,"{fecha} | {peso}kg"\n'
            f'TEXT 160,84,"1",0,1,1,"{uuid_qr}"\n'
            "PRINT 1,1\n"
        )

    @staticmethod
    def tspl_producto(datos: dict) -> str:
        """TSPL para producto 50x30mm."""
        uuid_qr   = datos.get("uuid_qr", "")
        contenido = f"SPJ:PROD:{uuid_qr}"
        nombre    = datos.get("nombre", "")[:25]
        precio    = float(datos.get("precio", 0))
        return (
            "SIZE 50 mm, 30 mm\n"
            "GAP 3 mm, 0 mm\n"
            "CLS\n"
            f'QRCODE 10,10,L,3,A,0,"{contenido}"\n'
            f'TEXT 120,10,"3",0,1,1,"{nombre}"\n'
            f'TEXT 120,30,"3",0,1,1,"${precio:.2f}/kg"\n'
            f'TEXT 120,55,"1",0,1,1,"{uuid_qr[:16]}"\n'
            "PRINT 1,1\n"
        )

    @classmethod
    def get_commands(cls, tipo: str, datos: dict,
                     formato: str = "zpl") -> str:
        """Punto de entrada: devuelve comandos según tipo y formato."""
        dispatch = {
            ("contenedor", "zpl"):  cls.zpl_contenedor,
            ("producto",   "zpl"):  cls.zpl_producto,
            ("fidelidad",  "zpl"):  cls.zpl_fidelidad,
            ("contenedor", "tspl"): cls.tspl_contenedor,
            ("producto",   "tspl"): cls.tspl_producto,
        }
        fn = dispatch.get((tipo, formato))
        if fn:
            return fn(datos)
        # fallback: ZPL generico
        return cls.zpl_contenedor(datos)
