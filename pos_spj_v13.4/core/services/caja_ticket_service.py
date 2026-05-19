# core/services/caja_ticket_service.py
"""
CajaTicketService — Impresión y generación de PDF para cortes Z.

Extrae lógica de impresión de modulos/caja.py.
La UI solo debe llamar:
    container.caja_ticket_service.preview_or_print_corte(resultado, parent_widget)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger("spj.caja.ticket")


class CajaTicketService:
    """Genera HTML, PDF y envía ESC/POS para comprobantes de corte Z."""

    def __init__(self, db=None, hardware_service=None):
        self.db = db
        self._hw = hardware_service

    def generar_html_corte(self, datos: Dict, cierre_id: int) -> str:
        """Genera el HTML del ticket de corte Z."""
        diferencia_texto = "Exacto ($0.00)"
        dif = float(datos.get("diferencia", 0))
        if dif < -0.01:
            diferencia_texto = f"<span style='color:red;'>FALTANTE: ${abs(dif):.2f}</span>"
        elif dif > 0.01:
            diferencia_texto = f"SOBRANTE: ${dif:.2f}"

        cajero = datos.get("cajero", "")
        fecha = datos.get("fecha", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ventas = float(datos.get("ventas_totales", datos.get("total_ventas", 0)))
        retiros = float(datos.get("retiros", 0))
        esperado = float(datos.get("esperado", datos.get("efectivo_esperado", 0)))
        contado = float(datos.get("contado", datos.get("efectivo_contado", 0)))
        fondo = float(datos.get("fondo_inicial", 0))

        return f"""
        <html>
        <body style="font-family:monospace;text-align:center;width:300px;">
            <h2>CORTE DE CAJA (Z)</h2>
            <p>=============================</p>
            <p><strong>Folio:</strong> {cierre_id}</p>
            <p><strong>Fecha:</strong> {fecha}</p>
            <p><strong>Cajero:</strong> {cajero}</p>
            <p>=============================</p>
            <div style="text-align:left;padding-left:20px;">
                <p>Fondo inicial: ${fondo:.2f}</p>
                <p>Ventas Totales: ${ventas:.2f}</p>
                <p>Gastos/Retiros: ${retiros:.2f}</p>
                <p>-------------------------</p>
                <p><strong>EFECTIVO ESPERADO: ${esperado:.2f}</strong></p>
                <p><strong>EFECTIVO CONTADO:  ${contado:.2f}</strong></p>
                <p>-------------------------</p>
                <h3>DIFERENCIA: {diferencia_texto}</h3>
            </div>
            <br><br>
            <p>_________________________</p>
            <p>Firma del Cajero</p>
        </body>
        </html>
        """

    def guardar_pdf(self, datos: Dict, cierre_id: int, carpeta: str = "CORTES_Z") -> str:
        """Guarda PDF del corte en la carpeta indicada. Retorna la ruta del archivo."""
        try:
            from PyQt5.QtPrintSupport import QPrinter
            from PyQt5.QtGui import QTextDocument
            os.makedirs(carpeta, exist_ok=True)
            fecha_str = datetime.now().strftime("%Y%m%d")
            filename = os.path.join(carpeta, f"corte_z_{cierre_id}_{fecha_str}.pdf")
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(filename)
            doc = QTextDocument()
            doc.setHtml(self.generar_html_corte(datos, cierre_id))
            doc.print_(printer)
            logger.info("PDF corte Z guardado: %s", filename)
            return filename
        except Exception as e:
            logger.warning("guardar_pdf: %s", e)
            return ""

    def enviar_escpos(self, datos: Dict, ancho: int = 48) -> bool:
        """Envía ticket ESC/POS a impresora térmica via HardwareService."""
        hw = self._hw
        if not hw:
            return False
        try:
            hw.load_configs()
            cfg = hw._cache_config.get("ticket", {})
            if not cfg:
                return False
            ubicacion = cfg.get("ubicacion", "")
            ancho = 48 if "80" in cfg.get("ancho", "80") else 32
            if not ubicacion:
                return False

            ESC = b"\x1b"
            GS = b"\x1d"
            data = bytearray()
            data += ESC + b"@"
            data += ESC + b"a\x01"
            data += ESC + b"E\x01"
            data += b"** CORTE Z **\n"
            data += ESC + b"E\x00"
            sep = b"-" * ancho + b"\n"
            data += sep
            data += f"Cajero: {datos.get('cajero','')}\n".encode()
            data += f"Fecha:  {datos.get('fecha','')}\n".encode()
            data += sep
            data += ESC + b"a\x00"
            ventas = float(datos.get("ventas_totales", datos.get("total_ventas", 0)))
            retiros = float(datos.get("retiros", 0))
            esperado = float(datos.get("esperado", datos.get("efectivo_esperado", 0)))
            contado = float(datos.get("contado", datos.get("efectivo_contado", 0)))
            dif = float(datos.get("diferencia", 0))
            data += f"Ventas:   ${ventas:>10,.2f}\n".encode()
            data += f"Retiros:  ${retiros:>10,.2f}\n".encode()
            data += sep
            data += ESC + b"E\x01"
            data += f"Esperado: ${esperado:>10,.2f}\n".encode()
            data += f"Contado:  ${contado:>10,.2f}\n".encode()
            data += sep
            dif_str = (
                "CUADRADO        " if abs(dif) < 0.01
                else (f"FALTANTE ${abs(dif):,.2f}" if dif < 0 else f"SOBRANTE ${dif:,.2f}")
            )
            data += f"DIFERENCIA: {dif_str}\n".encode()
            data += ESC + b"E\x00"
            data += b"\n\n\n"
            data += GS + b"V\x42\x00"

            tipo = cfg.get("tipo", "").lower()
            if "red" in tipo or ":" in ubicacion:
                import socket
                ip, port = ubicacion.split(":") if ":" in ubicacion else (ubicacion, "9100")
                s = socket.socket()
                s.settimeout(5)
                s.connect((ip.strip(), int(port)))
                s.sendall(bytes(data))
                s.close()
            elif "serial" in tipo or "com" in ubicacion.upper():
                import serial as _ser
                with _ser.Serial(ubicacion, 9600, timeout=3) as s:
                    s.write(bytes(data))
            else:
                try:
                    with open(ubicacion, "wb") as f:
                        f.write(bytes(data))
                except Exception:
                    return False
            return True
        except Exception as e:
            logger.warning("ESC/POS: %s", e)
            return False

    def preview_or_print_corte(self, resultado: Dict, cajero: str, parent=None) -> None:
        """
        Muestra diálogo de vista previa con opciones: imprimir + guardar PDF.
        Este es el único punto de entrada para impresión desde la UI.
        """
        datos = {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cajero": cajero,
            "ventas_totales": float(resultado.get("total_ventas", resultado.get("ventas_totales", 0))),
            "retiros": float(resultado.get("retiros", 0)),
            "esperado": float(resultado.get("efectivo_esperado", resultado.get("esperado", 0))),
            "contado": float(resultado.get("efectivo_contado", resultado.get("contado", 0))),
            "diferencia": float(resultado.get("diferencia", 0)),
            "fondo_inicial": float(resultado.get("fondo_inicial", 0)),
        }
        cierre_id = int(resultado.get("cierre_id", resultado.get("turno_id", 0)))

        # Auto-save PDF
        try:
            self.guardar_pdf(datos, cierre_id)
        except Exception as e:
            logger.warning("auto-save PDF: %s", e)

        # Show dialog
        try:
            from PyQt5.QtWidgets import (
                QDialog, QVBoxLayout, QHBoxLayout, QTextBrowser, QFileDialog,
            )
            from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
            from PyQt5.QtGui import QTextDocument

            try:
                from modulos.ui_components import (
                    create_primary_button, create_success_button, create_secondary_button,
                )
                from modulos.ui_components import Toast
            except Exception:
                return

            html = self.generar_html_corte(datos, cierre_id)
            dlg = QDialog(parent)
            dlg.setWindowTitle(f"Ticket Corte Z — {datos['cajero']}")
            dlg.setMinimumSize(420, 500)
            lay = QVBoxLayout(dlg)

            browser = QTextBrowser()
            browser.setHtml(html)
            lay.addWidget(browser)

            btn_row = QHBoxLayout()
            btn_print = create_primary_button(dlg, "🖨️ Imprimir", "Imprimir comprobante")
            btn_pdf = create_success_button(dlg, "💾 Guardar PDF", "Guardar como PDF")
            btn_close = create_secondary_button(dlg, "Cerrar", "Cerrar vista previa")

            def _do_print():
                if self.enviar_escpos(datos):
                    return
                printer = QPrinter(QPrinter.HighResolution)
                pdlg = QPrintDialog(printer, dlg)
                if pdlg.exec_() == QPrintDialog.Accepted:
                    doc = QTextDocument()
                    doc.setHtml(html)
                    doc.print_(printer)

            def _save_pdf():
                path, _ = QFileDialog.getSaveFileName(
                    dlg, "Guardar Corte Z",
                    f"CorteZ_{datos['cajero']}_{datos['fecha'][:10]}.pdf",
                    "PDF (*.pdf)",
                )
                if path:
                    printer = QPrinter(QPrinter.HighResolution)
                    printer.setOutputFormat(QPrinter.PdfFormat)
                    printer.setOutputFileName(path)
                    doc = QTextDocument()
                    doc.setHtml(html)
                    doc.print_(printer)
                    if parent:
                        Toast.success(parent, "PDF guardado", path)

            btn_print.clicked.connect(_do_print)
            btn_pdf.clicked.connect(_save_pdf)
            btn_close.clicked.connect(dlg.accept)

            btn_row.addWidget(btn_print)
            btn_row.addWidget(btn_pdf)
            btn_row.addStretch()
            btn_row.addWidget(btn_close)
            lay.addLayout(btn_row)
            dlg.exec_()
        except Exception as e:
            logger.warning("preview_or_print_corte: %s", e)
