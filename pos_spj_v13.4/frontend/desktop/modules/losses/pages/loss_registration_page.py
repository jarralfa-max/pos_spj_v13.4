"""LOSS-5 form. Business rules and persistence remain behind the presenter."""
from decimal import Decimal
from PyQt5.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.file_path_input import FilePathInput
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.product_search_box import ProductSearchBox
from frontend.desktop.components.quantity_input import QuantityInput
from frontend.desktop.components.search_selector import SearchSelector

class LossRegistrationPage(QWidget):
    def __init__(self, presenter, *, warehouse_id: str, parent=None):
        super().__init__(parent); self._presenter = presenter; self._warehouse_id = warehouse_id
        self._product_id = ""; self._lot_id = None; self._loaded = False
        root = QVBoxLayout(self)
        root.addWidget(PageHeader(title="Registro general de pérdidas", subtitle="Captura producto, lote, magnitud, causa y evidencia.", parent=self))
        form = QFormLayout(); self.product = ProductSearchBox(provider=presenter.search_products, parent=self)
        self.product.selected.connect(self._select_product)
        self.lot = SearchSelector(provider=lambda q: presenter.search_lots(self._product_id, q), placeholder="Buscar lote (opcional)...", parent=self)
        self.lot.selected.connect(lambda option: setattr(self, "_lot_id", option.id))
        self.quantity = QuantityInput(self, decimals=3); self.weight = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self.unit = QLineEdit("unit", self); self.classification = QComboBox(self); self.reason = QComboBox(self); self.origin = QComboBox(self)
        self.classification.currentIndexChanged.connect(self._load_reasons)
        for value, label in (("INVENTORY","Inventario"),("STORAGE","Almacenamiento"),("TRANSPORT","Transporte"),("QUALITY","Calidad"),("MANUAL_AUTHORIZED","Registro manual autorizado")):
            self.origin.addItem(label, value)
        self.evidence = FilePathInput(self, caption="Adjuntar evidencia", file_filter="Evidencia (*.jpg *.jpeg *.png *.pdf);;Todos (*.*)")
        self.notes = QPlainTextEdit(self)
        for label, widget in (("Producto *",self.product),("Lote",self.lot),("Cantidad",self.quantity),("Peso (kg)",self.weight),("Unidad *",self.unit),("Clasificación *",self.classification),("Causa *",self.reason),("Origen *",self.origin),("Evidencia",self.evidence),("Notas",self.notes)):
            form.addRow(label, widget)
        root.addLayout(form); self.status = QLabel("", self); root.addWidget(self.status)
        actions = QHBoxLayout(); draft = create_secondary_button(self,"Guardar borrador"); submit = create_primary_button(self,"Enviar a revisión")
        draft.clicked.connect(lambda: self._save(False)); submit.clicked.connect(lambda: self._save(True))
        actions.addStretch(1); actions.addWidget(draft); actions.addWidget(submit); root.addLayout(actions)
    def ensure_loaded(self):
        if self._loaded: return
        for identifier, label in self._presenter.classifications(): self.classification.addItem(label, identifier)
        self._loaded = True; self._load_reasons()
    def _select_product(self, option):
        self._product_id = option.id; self._lot_id = None; self.lot.clear()
    def _load_reasons(self):
        self.reason.clear(); classification_id = self.classification.currentData()
        if classification_id:
            for identifier, label, required in self._presenter.reasons(classification_id): self.reason.addItem(label, (identifier, required))
    def _save(self, submit):
        reason = self.reason.currentData(); quantity = self.quantity.decimal_value() or Decimal("0"); weight = self.weight.decimal_value() or Decimal("0")
        if not self._product_id or not self.classification.currentData() or not reason:
            QMessageBox.warning(self,"Datos incompletos","Selecciona producto, clasificación y causa."); return
        try:
            result = self._presenter.register(warehouse_id=self._warehouse_id, classification_id=self.classification.currentData(), reason_id=reason[0], origin=self.origin.currentData(), product_id=self._product_id, lot_id=self._lot_id, quantity=quantity, weight=weight, unit=self.unit.text().strip(), evidence_path=self.evidence.path(), notes=self.notes.toPlainText(), submit=submit)
        except Exception as exc:
            QMessageBox.critical(self,"No fue posible registrar",str(exc)); return
        self.status.setText(f"Expediente {result.case_id} · {result.status.value}")
        QMessageBox.information(self,"Registro guardado","La pérdida se registró correctamente.")
