# modulos/whatsapp/panels/diagnostics_panel.py
"""Panel Diagnóstico — pruebas de conectividad y log de eventos recientes."""
from __future__ import annotations

import datetime
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.spj_styles import spj_btn, apply_object_names
from modulos.whatsapp.panels._panel_styles import group_box_style
from modulos.whatsapp.widgets import StatusBadge

logger = logging.getLogger("spj.ui.wa.diagnostics_panel")


class _CheckRow(QWidget):
    """Fila de prueba: etiqueta + badge + botón."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(Spacing.SM)

        lbl = QLabel(label)
        lbl.setMinimumWidth(200)
        lbl.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_700};"
            f"font-size: {Typography.SIZE_MD};"
        )
        self._badge = StatusBadge("—", "neutral")

        lay.addWidget(lbl)
        lay.addWidget(self._badge)
        lay.addStretch()

    def set_ok(self, text: str = "OK") -> None:
        self._badge.set_status(text, "ok")

    def set_error(self, text: str = "Error") -> None:
        self._badge.set_status(text, "error")

    def set_loading(self, text: str = "Verificando…") -> None:
        self._badge.set_status(text, "loading")

    def set_neutral(self, text: str = "—") -> None:
        self._badge.set_status(text, "neutral")


class DiagnosticsPanel(QWidget):
    """Pruebas de conectividad y visor de log de diagnóstico."""

    def __init__(self, svc, cred_svc=None, container=None, parent=None) -> None:
        super().__init__(parent)
        self._svc       = svc
        self._cred      = cred_svc
        self._container = container
        self._build_ui()
        apply_object_names(self)

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.LG)

        # ── Pruebas de conectividad ───────────────────────────────────────────
        grp_checks = QGroupBox("Pruebas de conectividad")
        grp_checks.setStyleSheet(group_box_style())
        lay_ch = QVBoxLayout(grp_checks)
        lay_ch.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        lay_ch.setSpacing(Spacing.SM)

        self._row_api    = _CheckRow("Meta Cloud API")
        self._row_ms     = _CheckRow("Microservicio WhatsApp")
        self._row_rasa   = _CheckRow("Rasa NLU")
        self._row_webhook= _CheckRow("Webhook local")
        self._row_db     = _CheckRow("Base de datos ERP")

        for row in (self._row_api, self._row_ms, self._row_rasa,
                    self._row_webhook, self._row_db):
            lay_ch.addWidget(row)

        btn_run_all = QPushButton("Ejecutar todas las pruebas")
        spj_btn(btn_run_all, "primary")
        btn_run_all.clicked.connect(self._run_all)

        btn_lay = QHBoxLayout()
        btn_lay.addWidget(btn_run_all)
        btn_lay.addStretch()
        lay_ch.addLayout(btn_lay)
        root.addWidget(grp_checks)

        # ── Log de diagnóstico ────────────────────────────────────────────────
        grp_log = QGroupBox("Log de diagnóstico")
        grp_log.setStyleSheet(group_box_style())
        lay_log = QVBoxLayout(grp_log)
        lay_log.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(200)
        self._log.setStyleSheet(
            f"QTextEdit {{"
            f"  background: {Colors.NEUTRAL.SLATE_900};"
            f"  color: {Colors.NEUTRAL.SLATE_200};"
            f"  font-family: 'Courier New', monospace;"
            f"  font-size: {Typography.SIZE_SM};"
            f"  border: none;"
            f"  border-radius: {Borders.RADIUS_LG}px;"
            f"}}"
        )

        btn_clear = QPushButton("Limpiar log")
        spj_btn(btn_clear, "secondary")
        btn_clear.clicked.connect(self._log.clear)

        lay_log.addWidget(self._log)
        ctrl_log = QHBoxLayout()
        ctrl_log.addStretch()
        ctrl_log.addWidget(btn_clear)
        lay_log.addLayout(ctrl_log)
        root.addWidget(grp_log)

        # ── Info de versión ───────────────────────────────────────────────────
        grp_ver = QGroupBox("Información del sistema")
        grp_ver.setStyleSheet(group_box_style())
        lay_ver = QVBoxLayout(grp_ver)
        lay_ver.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)

        self._lbl_ver = QLabel("")
        self._lbl_ver.setWordWrap(True)
        self._lbl_ver.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500};"
            f"font-size: {Typography.SIZE_SM};"
        )
        self._populate_version_info()
        lay_ver.addWidget(self._lbl_ver)
        root.addWidget(grp_ver)
        root.addStretch()

    # ── Diagnósticos ──────────────────────────────────────────────────────────

    def _run_all(self) -> None:
        self._log_line("=== Iniciando diagnóstico ===")
        self._check_api()
        self._check_microservice()
        self._check_rasa()
        self._check_webhook()
        self._check_db()
        self._log_line("=== Diagnóstico completado ===\n")

    def _check_api(self) -> None:
        self._row_api.set_loading()
        try:
            ok = self._svc.test_connection()
            if ok:
                self._row_api.set_ok("Conectada")
                self._log_line("✅ Meta Cloud API — OK")
            else:
                self._row_api.set_error("Sin respuesta")
                self._log_line("❌ Meta Cloud API — Sin respuesta (verifica token y phone_id)")
        except Exception as exc:
            self._row_api.set_error("Error")
            self._log_line(f"❌ Meta Cloud API — Error: {exc}")

    def _check_microservice(self) -> None:
        self._row_ms.set_loading()
        try:
            import urllib.request
            cfg = self._svc.get_config if hasattr(self._svc, "get_config") else lambda k, d="": d
            ms_url = cfg("microservicio_url", "http://localhost:8000")
            resp = urllib.request.urlopen(f"{ms_url}/health", timeout=3)
            if resp.status == 200:
                self._row_ms.set_ok("Activo")
                self._log_line(f"✅ Microservicio WA ({ms_url}) — OK")
            else:
                self._row_ms.set_error(f"HTTP {resp.status}")
                self._log_line(f"⚠️  Microservicio WA — HTTP {resp.status}")
        except Exception as exc:
            self._row_ms.set_error("No disponible")
            self._log_line(f"❌ Microservicio WA — No disponible: {exc}")

    def _check_rasa(self) -> None:
        self._row_rasa.set_loading()
        try:
            import urllib.request
            cfg = self._svc.get_config if hasattr(self._svc, "get_config") else lambda k, d="": d
            rasa_url = cfg("rasa_url", "http://localhost:5005")
            resp = urllib.request.urlopen(f"{rasa_url}/", timeout=3)
            if resp.status == 200:
                self._row_rasa.set_ok("Activo")
                self._log_line(f"✅ Rasa NLU ({rasa_url}) — OK")
            else:
                self._row_rasa.set_error(f"HTTP {resp.status}")
                self._log_line(f"⚠️  Rasa NLU — HTTP {resp.status}")
        except Exception as exc:
            self._row_rasa.set_neutral("No configurado")
            self._log_line(f"ℹ️  Rasa NLU — No disponible: {exc}")

    def _check_webhook(self) -> None:
        self._row_webhook.set_loading()
        try:
            wa_hook = getattr(self._container, "whatsapp_webhook", None) if self._container else None
            running = wa_hook and getattr(wa_hook, "_running", False)
            if running:
                self._row_webhook.set_ok("Activo")
                self._log_line("✅ Webhook local — activo")
            else:
                self._row_webhook.set_neutral("Detenido")
                self._log_line("ℹ️  Webhook local — detenido (no bloquea operación)")
        except Exception as exc:
            self._row_webhook.set_error("Error")
            self._log_line(f"❌ Webhook local — Error: {exc}")

    def _check_db(self) -> None:
        self._row_db.set_loading()
        try:
            rows = self._svc.list_numeros()
            self._row_db.set_ok(f"OK ({len(rows)} número(s))")
            self._log_line(f"✅ Base de datos ERP — OK ({len(rows)} número(s))")
        except Exception as exc:
            self._row_db.set_error("Error DB")
            self._log_line(f"❌ Base de datos ERP — Error: {exc}")

    def _log_line(self, line: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.append(f"[{ts}] {line}")

    def _populate_version_info(self) -> None:
        import sys
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        try:
            from PyQt5.QtCore import QT_VERSION_STR
            qt_ver = QT_VERSION_STR
        except Exception:
            qt_ver = "—"
        self._lbl_ver.setText(
            f"Python {py_ver} | PyQt5 Qt {qt_ver} | SPJ POS v13.4 — Módulo WhatsApp"
        )
