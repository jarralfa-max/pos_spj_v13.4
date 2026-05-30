# modulos/config_hardware.py — SPJ POS
"""Módulo de configuración de hardware.

Este módulo usa HardwareConfigRepository como contrato canónico. La UI de
hardware y PrinterService leen/escriben la misma fuente de verdad:
``hardware_config``.
"""
from __future__ import annotations

import logging
from typing import Dict, Any

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QComboBox, QLineEdit, QCheckBox, QSpinBox, QTabWidget,
    QMessageBox,
)

from core.repositories.hardware_config_repository import HardwareConfigRepository
from modulos.design_tokens import Spacing

logger = logging.getLogger("spj.config_hardware")

_PORTS = [
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyS0", "/dev/ttyS1",
]
_BAUD = ["2400", "4800", "9600", "19200", "38400", "57600", "115200"]


class ModuloConfigHardware(QWidget):
    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self.db = container.db
        self.repo = HardwareConfigRepository(self.db)
        self.sucursal_id = 1
        try:
            self.repo.ensure_schema()
            self.repo.seed_defaults()
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            logger.exception("No se pudo asegurar hardware_config")
        self._init_ui()
        QTimer.singleShot(200, self._cargar_todo)

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        return None

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id

    def _init_ui(self):
        from modulos.ui_components import create_primary_button, create_heading_label

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)

        hdr = QHBoxLayout()
        hdr.addWidget(create_heading_label(self, "🔧 Configuración de Hardware"))
        hdr.addStretch()
        btn_save = create_primary_button(self, "💾 Guardar todo", "Guardar toda la configuración de hardware")
        btn_save.clicked.connect(self._guardar_todo)
        hdr.addWidget(btn_save)
        root.addLayout(hdr)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabWidget")
        root.addWidget(self.tabs)
        self.tabs.addTab(self._tab_bascula(), "⚖️  Báscula")
        self.tabs.addTab(self._tab_impresoras(), "🖨️  Impresoras")
        self.tabs.addTab(self._tab_cajon(), "💵  Cajón Dinero")
        self.tabs.addTab(self._tab_scanner(), "🔫  Escáner QR/CB")
        self.tabs.addTab(self._tab_red(), "🌐  Red")

    def _tab_bascula(self) -> QWidget:
        from modulos.ui_components import create_primary_button, create_combo
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(Spacing.SM)
        grp = QGroupBox("Configuración de báscula serial"); grp.setObjectName("styledGroup")
        form = QFormLayout(grp)
        self.chk_bascula = QCheckBox("Habilitar lectura automática de peso")
        self.cmb_bascula_puerto = create_combo(self, _PORTS)
        self.cmb_bascula_baud = create_combo(self, _BAUD); self.cmb_bascula_baud.setCurrentText("9600")
        self.cmb_bascula_proto = create_combo(self, ["Genérico (simple)", "Dibal", "Mettler-Toledo", "CAS", "Ohaus"])
        self.spin_bascula_intervalo = QSpinBox(); self.spin_bascula_intervalo.setRange(200, 5000); self.spin_bascula_intervalo.setValue(500); self.spin_bascula_intervalo.setSuffix(" ms"); self.spin_bascula_intervalo.setObjectName("inputField")
        form.addRow("", self.chk_bascula)
        form.addRow("Puerto serial:", self.cmb_bascula_puerto)
        form.addRow("Baudrate:", self.cmb_bascula_baud)
        form.addRow("Protocolo:", self.cmb_bascula_proto)
        form.addRow("Intervalo lectura:", self.spin_bascula_intervalo)
        lay.addWidget(grp)
        grp2 = QGroupBox("Prueba de conexión"); grp2.setObjectName("styledGroup")
        hl = QHBoxLayout(grp2)
        btn_test = create_primary_button(self, "🔌 Probar conexión", "Verificar conexión con la báscula")
        btn_test.clicked.connect(self._test_bascula)
        self.lbl_bascula_status = QLabel("—"); self.lbl_bascula_status.setObjectName("textSecondary")
        hl.addWidget(btn_test); hl.addWidget(self.lbl_bascula_status); hl.addStretch()
        lay.addWidget(grp2); lay.addStretch()
        return w

    def _tab_impresoras(self) -> QWidget:
        from modulos.ui_components import create_primary_button, create_input, create_combo
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(Spacing.SM)

        grp_ticket = QGroupBox("🧾 Impresora de tickets (térmica)"); grp_ticket.setObjectName("styledGroup")
        ft = QFormLayout(grp_ticket)
        self.cmb_ticket_tipo = create_combo(self, [
            "USB — win32print (Windows)",
            "USB — COM virtual (Adm. dispositivos)",
            "Red — IP:Puerto (TCP/IP)",
            "Serial — Puerto COM",
        ])
        self.cmb_ticket_tipo.currentIndexChanged.connect(self._ticket_tipo_changed)
        self.txt_ticket_ubicacion = create_input(self, "")
        self._ticket_tipo_changed(0)
        self.cmb_ticket_ancho = create_combo(self, ["58 mm (32 chars)", "80 mm (48 chars)"])
        self.chk_ticket_corte = QCheckBox("Corte automático al imprimir"); self.chk_ticket_corte.setChecked(True)
        self.chk_ticket_cajon = QCheckBox("Abrir cajón junto con ticket")
        ft.addRow("Tipo conexión:", self.cmb_ticket_tipo)
        ft.addRow("Ubicación/IP:", self.txt_ticket_ubicacion)
        ft.addRow("Ancho papel:", self.cmb_ticket_ancho)
        ft.addRow("", self.chk_ticket_corte)
        ft.addRow("", self.chk_ticket_cajon)
        hl_t = QHBoxLayout()
        btn_test_t = create_primary_button(self, "🖨️ Imprimir ticket de prueba", "Imprimir ticket de prueba para verificar configuración")
        btn_test_t.clicked.connect(self._test_ticket)
        self.lbl_ticket_status = QLabel("—"); self.lbl_ticket_status.setObjectName("textSecondary")
        hl_t.addWidget(btn_test_t); hl_t.addWidget(self.lbl_ticket_status); hl_t.addStretch()
        ft.addRow("", hl_t)
        lay.addWidget(grp_ticket)

        grp_etiq = QGroupBox("🏷️ Impresora de etiquetas (ZPL/EPL)"); grp_etiq.setObjectName("styledGroup")
        fe = QFormLayout(grp_etiq)
        self.cmb_etiq_tipo = create_combo(self, ["USB", "Serial (COM)", "Red (IP:Puerto)", "Sin impresora de etiquetas"])
        self.txt_etiq_ubicacion = create_input(self, ""); self.txt_etiq_ubicacion.setPlaceholderText("COM4  |  192.168.1.101:9100")
        self.cmb_etiq_lenguaje = create_combo(self, ["ZPL (Zebra)", "EPL (Eltron)", "TSPL (TSC)"])
        fe.addRow("Tipo conexión:", self.cmb_etiq_tipo)
        fe.addRow("Ubicación:", self.txt_etiq_ubicacion)
        fe.addRow("Lenguaje:", self.cmb_etiq_lenguaje)
        btn_test_e = create_primary_button(self, "🏷️ Imprimir etiqueta de prueba", "Imprimir etiqueta de prueba")
        btn_test_e.clicked.connect(self._test_etiqueta)
        fe.addRow("", btn_test_e)
        lay.addWidget(grp_etiq); lay.addStretch()
        return w

    def _tab_cajon(self) -> QWidget:
        from modulos.ui_components import create_warning_button, create_input, create_combo
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(Spacing.SM)
        grp = QGroupBox("Cajón de dinero (ESC/POS)"); grp.setObjectName("styledGroup")
        form = QFormLayout(grp)
        self.chk_cajon = QCheckBox("Cajón conectado (abrir automáticamente al cobrar)")
        self.cmb_cajon_metodo = create_combo(self, ["Por impresora de tickets (ESC/POS)", "Puerto serial directo", "Puerto paralelo (LPT)"])
        self.txt_cajon_cmd = create_input(self, "1B 70 00 19 FA")
        self.txt_cajon_cmd.setPlaceholderText("Hex: 1B 70 00 19 FA  (ESC p 0 25 250)")
        self.spin_cajon_delay = QSpinBox(); self.spin_cajon_delay.setRange(0, 2000); self.spin_cajon_delay.setValue(100); self.spin_cajon_delay.setSuffix(" ms después de cobrar"); self.spin_cajon_delay.setObjectName("inputField")
        form.addRow("", self.chk_cajon)
        form.addRow("Apertura vía:", self.cmb_cajon_metodo)
        form.addRow("Comando ESC/POS:", self.txt_cajon_cmd)
        form.addRow("Delay apertura:", self.spin_cajon_delay)
        lay.addWidget(grp)
        grp2 = QGroupBox("Prueba"); grp2.setObjectName("styledGroup")
        hl = QHBoxLayout(grp2)
        btn_abrir = create_warning_button(self, "💰 Abrir cajón ahora", "Abrir cajón de dinero manualmente")
        btn_abrir.clicked.connect(self._test_cajon)
        self.lbl_cajon_status = QLabel("—"); self.lbl_cajon_status.setObjectName("textSecondary")
        hl.addWidget(btn_abrir); hl.addWidget(self.lbl_cajon_status); hl.addStretch()
        lay.addWidget(grp2); lay.addStretch()
        return w

    def _tab_scanner(self) -> QWidget:
        from modulos.ui_components import create_input, create_combo
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(Spacing.SM)
        grp = QGroupBox("Escáner de código de barras / QR"); grp.setObjectName("styledGroup")
        form = QFormLayout(grp)
        self.cmb_scanner_modo = create_combo(self, ["HID Teclado (USB Plug & Play — recomendado)", "Serial (COM) — escáneres industriales", "Cámara web (software)"])
        self.cmb_scanner_puerto = QComboBox(); self.cmb_scanner_puerto.addItems(_PORTS)
        self.cmb_scanner_baud = QComboBox(); self.cmb_scanner_baud.addItems(_BAUD); self.cmb_scanner_baud.setCurrentText("9600")
        self.txt_scanner_prefijo = QLineEdit(); self.txt_scanner_prefijo.setPlaceholderText("(vacío = ninguno)")
        self.txt_scanner_sufijo = QLineEdit(); self.txt_scanner_sufijo.setPlaceholderText("\\r  ó  \\r\\n  (Enter)"); self.txt_scanner_sufijo.setText("\\r")
        self.chk_scanner_beep = QCheckBox("Beep al escanear (si el escáner lo soporta)"); self.chk_scanner_beep.setChecked(True)
        form.addRow("Modo:", self.cmb_scanner_modo)
        form.addRow("Puerto (serial):", self.cmb_scanner_puerto)
        form.addRow("Baudrate (serial):", self.cmb_scanner_baud)
        form.addRow("Prefijo esperado:", self.txt_scanner_prefijo)
        form.addRow("Sufijo/terminador:", self.txt_scanner_sufijo)
        form.addRow("", self.chk_scanner_beep)
        self.cmb_scanner_modo.currentIndexChanged.connect(lambda i: (self.cmb_scanner_puerto.setEnabled(i == 1), self.cmb_scanner_baud.setEnabled(i == 1)))
        self.cmb_scanner_puerto.setEnabled(False); self.cmb_scanner_baud.setEnabled(False)
        lay.addWidget(grp)
        grp2 = QGroupBox("Prueba — escanea un código aquí"); grp2.setObjectName("styledGroup")
        vt = QVBoxLayout(grp2)
        self.txt_scanner_test = create_input(self, ""); self.txt_scanner_test.setPlaceholderText("Coloca el cursor aquí y escanea un código...")
        self.lbl_scanner_result = QLabel("—"); self.lbl_scanner_result.setObjectName("textSuccess")
        self.txt_scanner_test.textChanged.connect(lambda t: self.lbl_scanner_result.setText(f"✅ Código: {t}" if t else "—"))
        vt.addWidget(QLabel("Escanea en el campo:")); vt.addWidget(self.txt_scanner_test); vt.addWidget(self.lbl_scanner_result)
        lay.addWidget(grp2); lay.addStretch()
        return w

    def _tab_red(self) -> QWidget:
        from modulos.ui_components import create_primary_button, create_secondary_button, create_input
        w = QWidget(); lay = QVBoxLayout(w); lay.setSpacing(Spacing.SM)
        grp = QGroupBox("Configuración de red del equipo POS"); grp.setObjectName("styledGroup")
        form = QFormLayout(grp)
        self.txt_red_ip = create_input(self, ""); self.txt_red_ip.setPlaceholderText("192.168.1.10")
        self.txt_red_mascara = create_input(self, ""); self.txt_red_mascara.setPlaceholderText("255.255.255.0")
        self.txt_red_gateway = create_input(self, ""); self.txt_red_gateway.setPlaceholderText("192.168.1.1")
        self.txt_red_dns = create_input(self, ""); self.txt_red_dns.setPlaceholderText("8.8.8.8")
        self.txt_red_nombre = create_input(self, ""); self.txt_red_nombre.setPlaceholderText("SPJ-POS-01")
        form.addRow("IP del equipo:", self.txt_red_ip)
        form.addRow("Máscara:", self.txt_red_mascara)
        form.addRow("Gateway:", self.txt_red_gateway)
        form.addRow("DNS:", self.txt_red_dns)
        form.addRow("Nombre equipo:", self.txt_red_nombre)
        lay.addWidget(grp)
        grp2 = QGroupBox("Diagnóstico de red"); grp2.setObjectName("styledGroup")
        hl2 = QHBoxLayout(grp2)
        btn_ping = create_primary_button(self, "📡 Ping al gateway", "Verificar conectividad con el gateway")
        btn_ping.clicked.connect(self._test_ping)
        btn_info = create_secondary_button(self, "ℹ️ Ver IP actual", "Mostrar información de red actual")
        btn_info.clicked.connect(self._ver_ip_actual)
        self.lbl_red_status = QLabel("—"); self.lbl_red_status.setObjectName("textSecondary")
        hl2.addWidget(btn_ping); hl2.addWidget(btn_info); hl2.addWidget(self.lbl_red_status); hl2.addStretch()
        lay.addWidget(grp2); lay.addStretch()
        return w

    def _cargar_todo(self):
        try:
            self.repo.ensure_schema()
            self.repo.seed_defaults()
            cfg_map = {tipo: self.repo.get_config(tipo) for tipo in ("bascula", "ticket", "etiquetas", "cajon", "scanner", "red")}
        except Exception as exc:
            logger.exception("No se pudo cargar hardware_config: %s", exc)
            QMessageBox.critical(self, "Error", f"No se pudo cargar configuración de hardware:\n{exc}")
            return

        b = cfg_map.get("bascula", {})
        self.chk_bascula.setChecked(bool(b.get("activo", False)))
        self.cmb_bascula_puerto.setCurrentText(b.get("puerto", "COM3"))
        self.cmb_bascula_baud.setCurrentText(str(b.get("baud", b.get("baud_rate", "9600"))))
        self.cmb_bascula_proto.setCurrentText(b.get("protocolo", "Genérico (simple)"))
        self.spin_bascula_intervalo.setValue(int(b.get("intervalo", 500)))

        t = cfg_map.get("ticket", {})
        self.txt_ticket_ubicacion.setText(t.get("ubicacion", ""))
        self.cmb_ticket_ancho.setCurrentText(t.get("ancho", "80 mm (48 chars)"))
        self.chk_ticket_corte.setChecked(bool(t.get("corte", True)))
        self.chk_ticket_cajon.setChecked(bool(t.get("abrir_cajon", False)))
        try:
            self.cmb_ticket_tipo.setCurrentIndex(int(t.get("tipo_idx", 0)))
        except Exception:
            pass

        e = cfg_map.get("etiquetas", {})
        self.txt_etiq_ubicacion.setText(e.get("ubicacion", ""))
        self.cmb_etiq_lenguaje.setCurrentText(e.get("lenguaje", "ZPL (Zebra)"))

        c = cfg_map.get("cajon", {})
        self.chk_cajon.setChecked(bool(c.get("activo", False)))
        self.txt_cajon_cmd.setText(c.get("comando", "1B 70 00 19 FA"))
        self.spin_cajon_delay.setValue(int(c.get("delay", 100)))

        sc = cfg_map.get("scanner", {})
        self.txt_scanner_prefijo.setText(sc.get("prefijo", ""))
        self.txt_scanner_sufijo.setText(sc.get("sufijo", "\\r"))

        rd = cfg_map.get("red", {})
        self.txt_red_ip.setText(rd.get("ip", ""))
        self.txt_red_mascara.setText(rd.get("mascara", "255.255.255.0"))
        self.txt_red_gateway.setText(rd.get("gateway", ""))
        self.txt_red_dns.setText(rd.get("dns", "8.8.8.8"))
        self.txt_red_nombre.setText(rd.get("nombre", "SPJ-POS-01"))

    def _guardar_todo(self):
        configs: Dict[str, Dict[str, Any]] = {
            "bascula": {
                "activo": self.chk_bascula.isChecked(),
                "puerto": self.cmb_bascula_puerto.currentText(),
                "baud": self.cmb_bascula_baud.currentText(),
                "protocolo": self.cmb_bascula_proto.currentText(),
                "intervalo": self.spin_bascula_intervalo.value(),
            },
            "ticket": {
                "tipo": self.cmb_ticket_tipo.currentText(),
                "tipo_idx": self.cmb_ticket_tipo.currentIndex(),
                "ubicacion": self.txt_ticket_ubicacion.text().strip(),
                "ancho": self.cmb_ticket_ancho.currentText(),
                "corte": self.chk_ticket_corte.isChecked(),
                "abrir_cajon": self.chk_ticket_cajon.isChecked(),
            },
            "etiquetas": {
                "tipo": self.cmb_etiq_tipo.currentText(),
                "ubicacion": self.txt_etiq_ubicacion.text().strip(),
                "lenguaje": self.cmb_etiq_lenguaje.currentText(),
            },
            "cajon": {
                "activo": self.chk_cajon.isChecked(),
                "metodo": self.cmb_cajon_metodo.currentText(),
                "comando": self.txt_cajon_cmd.text().strip(),
                "delay": self.spin_cajon_delay.value(),
            },
            "scanner": {
                "modo": self.cmb_scanner_modo.currentText(),
                "puerto": self.cmb_scanner_puerto.currentText(),
                "baud": self.cmb_scanner_baud.currentText(),
                "prefijo": self.txt_scanner_prefijo.text(),
                "sufijo": self.txt_scanner_sufijo.text(),
                "beep": self.chk_scanner_beep.isChecked(),
            },
            "red": {
                "ip": self.txt_red_ip.text().strip(),
                "mascara": self.txt_red_mascara.text().strip(),
                "gateway": self.txt_red_gateway.text().strip(),
                "dns": self.txt_red_dns.text().strip(),
                "nombre": self.txt_red_nombre.text().strip(),
            },
        }
        try:
            for tipo, cfg in configs.items():
                self.repo.save_config(tipo, HardwareConfigRepository.DEFAULT_TYPES.get(tipo, tipo.capitalize()), cfg, activo=1)
            self.db.commit()
            self._reload_runtime_services()
            QMessageBox.information(self, "✅ Guardado", "Configuración de hardware guardada y aplicada.")
        except Exception as exc:
            logger.exception("No se pudo guardar hardware_config")
            QMessageBox.critical(self, "Error", str(exc))

    def _reload_runtime_services(self) -> None:
        hw = getattr(self.container, "hardware_service", None)
        if hw:
            try:
                hw.load_configs()
            except Exception:
                logger.exception("No se pudo recargar HardwareService")
        printer = getattr(self.container, "printer_service", None)
        if printer:
            try:
                printer.reload_configs()
            except Exception:
                logger.exception("No se pudo recargar PrinterService")

    def _test_bascula(self):
        port = self.cmb_bascula_puerto.currentText(); baud = int(self.cmb_bascula_baud.currentText())
        try:
            import serial
            with serial.Serial(port, baud, timeout=2) as s:
                data = s.read(10)
            self.lbl_bascula_status.setText(f"✅ Puerto {port} OK — {len(data)} bytes recibidos")
            self.lbl_bascula_status.setObjectName("textSuccess")
        except ImportError:
            self.lbl_bascula_status.setText("⚠️  pyserial no instalado — pip install pyserial")
            self.lbl_bascula_status.setObjectName("textWarning")
        except Exception as exc:
            self.lbl_bascula_status.setText(f"❌ {str(exc)[:60]}")
            self.lbl_bascula_status.setObjectName("textDanger")

    def _test_ticket_printer(self):
        self._test_ticket()

    def _ticket_tipo_changed(self, idx: int = None) -> None:
        if idx is None:
            idx = self.cmb_ticket_tipo.currentIndex()
        placeholders = {
            0: "Epson TM-T20  (nombre exacto en Dispositivos e Impresoras de Windows)",
            1: "COM3  (ver Administrador de dispositivos → Puertos COM y LPT)",
            2: "192.168.1.100:9100  (IP:Puerto de la impresora en red)",
            3: "COM1  (puerto serial RS-232 físico)",
        }
        if hasattr(self, "txt_ticket_ubicacion"):
            self.txt_ticket_ubicacion.setPlaceholderText(placeholders.get(idx, ""))

    def _escpos_test_bytes(self) -> bytes:
        ESC = b"\x1b"; GS = b"\x1d"
        data = bytearray()
        data += ESC + b"@"
        data += ESC + b"a\x01"
        data += b"** SPJ POS **\nPrueba de impresora\n------------------\n"
        data += ESC + b"a\x00"
        data += b"Conexion: OK\n\n\n\n"
        data += GS + b"V\x42\x00"
        return bytes(data)

    def _test_ticket(self):
        # Persist first so the test exercises the same canonical path used by PrinterService.
        self._guardar_solo_ticket_sin_dialogo()
        printer = getattr(self.container, "printer_service", None)
        if not printer:
            self.lbl_ticket_status.setText("❌ PrinterService no disponible")
            self.lbl_ticket_status.setObjectName("textDanger")
            return
        printer.reload_configs()
        vr = printer.validate_ticket_printer_config()
        if not vr.ok:
            self.lbl_ticket_status.setText(f"❌ {'; '.join(vr.errors)[:90]}")
            self.lbl_ticket_status.setObjectName("textDanger")
            return
        job_id = printer.print_test_ticket()
        self.lbl_ticket_status.setText(f"✅ Ticket enviado a cola: {job_id}" if job_id else "❌ No se pudo encolar ticket")
        self.lbl_ticket_status.setObjectName("textSuccess" if job_id else "textDanger")

    def _guardar_solo_ticket_sin_dialogo(self) -> None:
        cfg = {
            "tipo": self.cmb_ticket_tipo.currentText(),
            "tipo_idx": self.cmb_ticket_tipo.currentIndex(),
            "ubicacion": self.txt_ticket_ubicacion.text().strip(),
            "ancho": self.cmb_ticket_ancho.currentText(),
            "corte": self.chk_ticket_corte.isChecked(),
            "abrir_cajon": self.chk_ticket_cajon.isChecked(),
        }
        self.repo.save_config("ticket", HardwareConfigRepository.DEFAULT_TYPES["ticket"], cfg, activo=1)
        self.db.commit()

    def _test_etiqueta(self):
        QMessageBox.information(self, "Prueba etiquetas", "Guarda la configuración y prueba desde el módulo de Etiquetas.")

    def _test_cajon(self):
        metodo = self.cmb_cajon_metodo.currentText(); cmd_hex = self.txt_cajon_cmd.text().strip()
        try:
            cmd_bytes = bytes(int(x, 16) for x in cmd_hex.split())
        except Exception:
            QMessageBox.warning(self, "Error", "Formato de comando inválido.\nEjemplo: 1B 70 00 19 FA")
            return
        try:
            ubicacion = self.txt_ticket_ubicacion.text().strip()
            if "impresora" in metodo.lower() and ":" in ubicacion:
                import socket
                ip, port = ubicacion.split(":", 1)
                with socket.socket() as s:
                    s.settimeout(3); s.connect((ip, int(port))); s.sendall(cmd_bytes)
            else:
                import serial
                port = ubicacion if "impresora" in metodo.lower() else self.cmb_bascula_puerto.currentText()
                with serial.Serial(port, 9600, timeout=2) as s:
                    s.write(cmd_bytes)
            self.lbl_cajon_status.setText("✅ Comando enviado")
            self.lbl_cajon_status.setObjectName("textSuccess")
        except Exception as exc:
            self.lbl_cajon_status.setText(f"❌ {str(exc)[:60]}")
            self.lbl_cajon_status.setObjectName("textDanger")

    def _test_ping(self):
        gateway = self.txt_red_gateway.text().strip()
        if not gateway:
            QMessageBox.warning(self, "Aviso", "Ingresa el gateway primero.")
            return
        import subprocess, platform
        param = "-n" if platform.system().lower() == "windows" else "-c"
        try:
            result = subprocess.run(["ping", param, "1", gateway], capture_output=True, text=True, timeout=5)
            self.lbl_red_status.setText(f"✅ {gateway} responde" if result.returncode == 0 else f"❌ {gateway} sin respuesta")
            self.lbl_red_status.setObjectName("textSuccess" if result.returncode == 0 else "textDanger")
        except Exception as exc:
            self.lbl_red_status.setText(f"❌ {str(exc)[:50]}")
            self.lbl_red_status.setObjectName("textDanger")

    def _ver_ip_actual(self):
        try:
            import socket
            self.lbl_red_status.setText(f"IP actual: {socket.gethostbyname(socket.gethostname())}  ({socket.gethostname()})")
            self.lbl_red_status.setObjectName("textPrimary")
        except Exception as exc:
            self.lbl_red_status.setText(f"Error: {exc}")
