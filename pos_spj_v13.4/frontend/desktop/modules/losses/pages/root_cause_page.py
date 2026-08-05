"""Spanish desktop form for LOSS-16; all data access stays behind its presenter."""

from PyQt5.QtWidgets import (QComboBox,QFormLayout,QHBoxLayout,QLabel,QListWidget,
                             QMessageBox,QPlainTextEdit,QPushButton,QVBoxLayout,QWidget)
from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.search_selector import SearchSelector


class RootCausePage(QWidget):
    def __init__(self,presenter,parent=None):
        super().__init__(parent); self._presenter=presenter
        self._investigation_id=""; self._primary=None; self._contributor=None; self._contributors=[]
        root=QVBoxLayout(self)
        root.addWidget(PageHeader(title="Análisis de causa raíz",
            subtitle="Documenta la causa primaria y los factores contribuyentes.",parent=self))
        form=QFormLayout()
        self.investigation=SearchSelector(provider=presenter.search_investigations,
            placeholder="Buscar investigación abierta...",parent=self)
        self.investigation.selected.connect(lambda option:setattr(self,"_investigation_id",option.id))
        self.method=QComboBox(self)
        for value,label in presenter.methods(): self.method.addItem(label,value.value)
        self.summary=QPlainTextEdit(self)
        self.primary=SearchSelector(provider=presenter.search_catalog,
            placeholder="Buscar causa primaria...",parent=self)
        self.primary.selected.connect(lambda option:setattr(self,"_primary",option))
        self.primary_reason=QPlainTextEdit(self)
        self.contributor=SearchSelector(provider=presenter.search_catalog,
            placeholder="Buscar causa contribuyente...",parent=self)
        self.contributor.selected.connect(lambda option:setattr(self,"_contributor",option))
        self.contributor_reason=QPlainTextEdit(self); self.contributor_list=QListWidget(self)
        add=QPushButton("Agregar causa contribuyente",self); add.clicked.connect(self._add_contributor)
        contributor_box=QVBoxLayout(); contributor_box.addWidget(self.contributor)
        contributor_box.addWidget(QLabel("Justificación",self)); contributor_box.addWidget(self.contributor_reason)
        contributor_box.addWidget(add); contributor_box.addWidget(self.contributor_list)
        for label,widget in (("Investigación *",self.investigation),("Método *",self.method),
            ("Resumen del análisis *",self.summary),("Causa primaria *",self.primary),
            ("Justificación primaria *",self.primary_reason)):
            form.addRow(label,widget)
        form.addRow("Causas contribuyentes",contributor_box)
        root.addLayout(form); self.status=QLabel("",self); root.addWidget(self.status)
        actions=QHBoxLayout(); actions.addStretch(1); save=create_primary_button(self,"Registrar causa raíz")
        save.clicked.connect(self._save); actions.addWidget(save); root.addLayout(actions)
    def _add_contributor(self):
        reason=self.contributor_reason.toPlainText().strip()
        if self._contributor is None or not reason:
            QMessageBox.warning(self,"Datos incompletos","Selecciona y justifica la causa contribuyente."); return
        if self._primary and self._contributor.id==self._primary.id or any(item[0]==self._contributor.id for item in self._contributors):
            QMessageBox.warning(self,"Causa duplicada","Cada causa debe ser distinta."); return
        self._contributors.append((self._contributor.id,reason))
        self.contributor_list.addItem(f"{self._contributor.label} — {reason}")
        self._contributor=None; self.contributor.clear(); self.contributor_reason.clear()
    def _save(self):
        primary_reason=self.primary_reason.toPlainText().strip()
        if not self._investigation_id or self._primary is None or not primary_reason or not self.summary.toPlainText().strip():
            QMessageBox.warning(self,"Datos incompletos","Selecciona investigación, causa primaria y completa el análisis."); return
        try:
            result=self._presenter.record(investigation_id=self._investigation_id,
                method=self.method.currentData(),summary=self.summary.toPlainText(),
                primary=(self._primary.id,primary_reason),contributors=tuple(self._contributors))
        except Exception as exc:
            QMessageBox.critical(self,"No fue posible registrar",str(exc)); return
        self.status.setText(f"Análisis {result.entity_id} · registrado")
        QMessageBox.information(self,"Causa raíz registrada","El análisis quedó vinculado a la investigación.")
