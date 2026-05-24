from __future__ import annotations
import asyncio
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QCheckBox, QMessageBox, QPlainTextEdit
)

from modulos.spj_styles import spj_btn
from ai.intent_resolver import IntentResolver
from parser.product_matcher import ProductMatcher
from parser.intent_parser import IntentParser
from parser.llm_local import OllamaClient
from models.message import IncomingMessage, MessageType
from models.context import ConversationContext
from datetime import datetime


class AIIntentPanel(QWidget):
    """Configuración de IA de intención (UI en español)."""

    def __init__(self, svc, db, parent=None):
        super().__init__(parent)
        self._svc = svc
        self._db = db
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        box = QGroupBox("IA de intención")
        lay = QVBoxLayout(box)

        self.chk_enabled = QCheckBox("Activar IA")
        self.txt_provider = QLineEdit(); self.txt_provider.setPlaceholderText("Proveedor (ej. mock/openai)")
        self.txt_model = QLineEdit(); self.txt_model.setPlaceholderText("Modelo")
        self.txt_api_key = QLineEdit(); self.txt_api_key.setPlaceholderText("Clave API")
        self.txt_api_key.setEchoMode(QLineEdit.Password)
        self.txt_conf = QLineEdit(); self.txt_conf.setPlaceholderText("Confianza mínima (0.75)")
        self.txt_timeout = QLineEdit(); self.txt_timeout.setPlaceholderText("Timeout en segundos (4)")
        self.chk_fallback = QCheckBox("Usar fallback local")

        self.lbl_status = QLabel("Estado IA: —")
        self.lbl_last_error = QLabel("Último error: —")
        self.test_input = QLineEdit("quiero 2 kilos de pechuga para mañana a las 10")
        self.test_output = QPlainTextEdit(); self.test_output.setReadOnly(True)

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("Guardar IA")
        self.btn_test = QPushButton("Probar IA")
        spj_btn(self.btn_save, "success")
        spj_btn(self.btn_test, "info")
        btn_row.addWidget(self.btn_save); btn_row.addWidget(self.btn_test); btn_row.addStretch()

        for w in [self.chk_enabled, self.txt_provider, self.txt_model, self.txt_api_key,
                  self.txt_conf, self.txt_timeout, self.chk_fallback,
                  self.lbl_status, self.lbl_last_error,
                  QLabel("Prueba de interpretación"), self.test_input, self.test_output]:
            lay.addWidget(w)
        lay.addLayout(btn_row)
        root.addWidget(box)

        self.btn_save.clicked.connect(self._save)
        self.btn_test.clicked.connect(self._test)

    def _load(self):
        cfg = lambda k, d="": self._svc.get_config(k, d)
        self.chk_enabled.setChecked(cfg("ai_intent_enabled", "0") == "1")
        self.txt_provider.setText(cfg("ai_provider", "mock"))
        self.txt_model.setText(cfg("ai_model", "mock-intent-v1"))
        self.txt_api_key.setText(cfg("ai_api_key", ""))
        self.txt_conf.setText(cfg("ai_min_confidence", "0.75"))
        self.txt_timeout.setText(cfg("ai_timeout_seconds", "4"))
        self.chk_fallback.setChecked(cfg("ai_fallback_enabled", "1") == "1")
        estado = "IA activa" if self.chk_enabled.isChecked() else "IA desactivada"
        if self.chk_enabled.isChecked() and self.chk_fallback.isChecked():
            estado = "IA con fallback"
        self.lbl_status.setText(f"Estado IA: {estado}")
        self.lbl_last_error.setText(f"Último error: {cfg("ai_last_error", "") or "—"}")

    def _save(self):
        self._svc.save_bot_config({
            "ai_intent_enabled": "1" if self.chk_enabled.isChecked() else "0",
            "ai_provider": self.txt_provider.text().strip() or "mock",
            "ai_model": self.txt_model.text().strip() or "mock-intent-v1",
            "ai_api_key": self.txt_api_key.text().strip(),
            "ai_min_confidence": self.txt_conf.text().strip() or "0.75",
            "ai_timeout_seconds": self.txt_timeout.text().strip() or "4",
            "ai_fallback_enabled": "1" if self.chk_fallback.isChecked() else "0",
        })
        QMessageBox.information(self, "IA de intención", "Configuración guardada.")
        self._load()

    def _test(self):
        matcher = ProductMatcher(self._db, sucursal_id=1)
        parser = IntentParser(matcher, llm_client=OllamaClient())
        resolver = IntentResolver(parser=parser, db=self._db)
        msg = IncomingMessage(
            message_id="test", from_number="521000000000", phone_number_id="test",
            timestamp=datetime.now(), type=MessageType.TEXT, text=self.test_input.text().strip()
        )
        ctx = ConversationContext(phone=msg.from_number)
        parsed = asyncio.run(resolver.resolve(msg, ctx))
        lines = [
            f"Intención detectada: {parsed.intent}",
            f"Confianza: {getattr(parsed, 'confidence', 0):.2f}",
            f"Productos: {getattr(parsed, 'products', [])}",
            f"Fecha programada: {getattr(parsed, 'scheduled_at', '')}",
            f"Tipo de entrega: {getattr(parsed, 'delivery_type', '')}",
            f"Pregunta de aclaración: {getattr(parsed, 'clarification_question', '')}",
            f"Fuente: {getattr(parsed, 'source', 'local')}",
        ]
        self.test_output.setPlainText("\n".join(lines))
        self._load()

