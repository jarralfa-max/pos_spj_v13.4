"""Clasificación cárnica — especies, regiones anatómicas y cortes (§11, PROD-22).

UI only: elige una especie y administra sus regiones anatómicas y su jerarquía
de cortes (canal → primario → secundario → porcionado). Todo cambio pasa por el
presenter de clasificación cárnica → casos de uso canónicos (con auditoría).
Ninguna especie está escrita en el código: salen del catálogo `species`.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.buttons import (
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.cards import SectionCard
from frontend.desktop.components.dialogs import MessageDialog, StandardDialog
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.components.tabs import Tabs
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.modules.products.dialogs.auto_code import (
    AutoCodeBinder,
    catalog_suggester,
)
from frontend.desktop.modules.products.meat_classification_presenter import (
    BONE_STATUS_ES,
    CUT_LEVEL_ES,
    FAT_CLASS_ES,
)
from frontend.desktop.themes.tokens import Spacing


def _estado(active) -> str:
    return "Activo" if active in (True, 1, "ACTIVE") else "Inactivo"


class MeatClassificationPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("meatClassificationPage")
        self._meat = getattr(presenter, "meat", None)
        self._presenter = presenter  # PROD-23: sugiere códigos de catálogo
        self._species: list[dict] = []
        self._regions: list[dict] = []
        self._cuts: list[dict] = []

        # Desbordamiento explícito (design system): a 1366×768 la página hace
        # scroll en lugar de recortar controles.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.viewport = PageViewport(self)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(PageHeader(
            title="Clasificación cárnica",
            subtitle="Especies, regiones anatómicas y jerarquía de cortes por especie.",
            icon=getattr(Icons, "CATALOG", None), compact=True))

        species_bar = QHBoxLayout()
        species_bar.addWidget(QLabel("Especie"))
        self.species_combo = QComboBox()
        self.species_combo.setObjectName("meatSpeciesCombo")
        self.species_combo.setAccessibleName("Especie")
        self.species_combo.setMinimumWidth(240)
        self.species_combo.currentIndexChanged.connect(lambda _i: self._load_species_detail())
        species_bar.addWidget(self.species_combo, 1)
        self.btn_new_species = create_secondary_button(self, "Nueva especie")
        self.btn_toggle_species = create_secondary_button(self, "Activar/Desactivar especie")
        species_bar.addWidget(self.btn_new_species)
        species_bar.addWidget(self.btn_toggle_species)
        layout.addLayout(species_bar)
        self.btn_new_species.clicked.connect(self._new_species)
        self.btn_toggle_species.clicked.connect(self._toggle_species)

        self.tabs = Tabs(self)
        self.tabs.addTab(self._build_regions_tab(), "Regiones anatómicas")
        self.tabs.addTab(self._build_cuts_tab(), "Cortes")
        layout.addWidget(self.tabs, 1)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setProperty("role", "banner")
        self.message.hide()
        layout.addWidget(self.message)

        self.viewport.set_page(body)
        outer.addWidget(self.viewport)
        manage = self._meat is not None
        self.btn_new_species.setEnabled(manage and self._meat.can_manage_species)
        self.btn_toggle_species.setEnabled(manage and self._meat.can_manage_species)
        self.btn_new_region.setEnabled(manage and self._meat.can_manage_regions)
        self.btn_toggle_region.setEnabled(manage and self._meat.can_manage_regions)
        self.btn_new_cut.setEnabled(manage and self._meat.can_manage_cuts)
        self.btn_toggle_cut.setEnabled(manage and self._meat.can_manage_cuts)
        self.refresh()

    # ── construcción ─────────────────────────────────────────────────────
    def _build_regions_tab(self) -> QWidget:
        tab = SectionCard(self)
        bar = QHBoxLayout()
        self.btn_new_region = create_primary_button(self, "Nueva región")
        self.btn_toggle_region = create_secondary_button(self, "Activar/Desactivar")
        bar.addWidget(self.btn_new_region)
        bar.addWidget(self.btn_toggle_region)
        bar.addStretch(1)
        tab.body().addLayout(bar)
        self.regions_table = StandardTable(columns=[
            ColumnSpec("Código", "text"), ColumnSpec("Nombre", "text"),
            ColumnSpec("Estado", "status")])
        tab.add(self.regions_table)
        self.btn_new_region.clicked.connect(self._new_region)
        self.btn_toggle_region.clicked.connect(self._toggle_region)
        return tab

    def _build_cuts_tab(self) -> QWidget:
        tab = SectionCard(self)
        bar = QHBoxLayout()
        self.btn_new_cut = create_primary_button(self, "Nuevo corte")
        self.btn_toggle_cut = create_secondary_button(self, "Activar/Desactivar")
        bar.addWidget(self.btn_new_cut)
        bar.addWidget(self.btn_toggle_cut)
        bar.addStretch(1)
        tab.body().addLayout(bar)
        self.cuts_table = StandardTable(columns=[
            ColumnSpec("Código", "text"), ColumnSpec("Nombre", "text"),
            ColumnSpec("Nivel", "text"), ColumnSpec("Región", "text"),
            ColumnSpec("Hueso", "text"), ColumnSpec("Grasa", "text"),
            ColumnSpec("Corte padre", "text"), ColumnSpec("Estado", "status")])
        tab.add(self.cuts_table)
        self.btn_new_cut.clicked.connect(self._new_cut)
        self.btn_toggle_cut.clicked.connect(self._toggle_cut)
        return tab

    # ── datos ────────────────────────────────────────────────────────────
    def refresh(self) -> None:
        if self._meat is None:
            self._show("La clasificación cárnica no está disponible.", ok=False)
            return
        current = self.species_combo.currentData()
        self._species = self._meat.species()
        self.species_combo.blockSignals(True)
        self.species_combo.clear()
        for s in self._species:
            suffix = "" if s.get("active") else " (inactiva)"
            self.species_combo.addItem(f"{s['name']}{suffix}", s["id"])
        index = max(0, self.species_combo.findData(current)) if current else 0
        self.species_combo.setCurrentIndex(index if self._species else -1)
        self.species_combo.blockSignals(False)
        self._load_species_detail()

    def _species_id(self) -> str | None:
        return self.species_combo.currentData()

    def _load_species_detail(self) -> None:
        species_id = self._species_id()
        self._regions = self._meat.regions(species_id) if species_id else []
        self._cuts = self._meat.cuts(species_id) if species_id else []
        self.regions_table.load_rows(
            [[r["code"], r["name"], _estado(r.get("active"))] for r in self._regions],
            row_ids=[r["id"] for r in self._regions])
        region_name = {r["id"]: r["name"] for r in self._regions}
        cut_name = {c["id"]: c["name"] for c in self._cuts}
        self.cuts_table.load_rows(
            [[c["code"], c["name"], CUT_LEVEL_ES.get(c["cut_level"], c["cut_level"]),
              region_name.get(c.get("anatomical_region_id"), ""),
              BONE_STATUS_ES.get(c.get("bone_status"), c.get("bone_status") or ""),
              FAT_CLASS_ES.get(c.get("fat_class"), c.get("fat_class") or ""),
              cut_name.get(c.get("parent_cut_id"), ""), _estado(c.get("status"))]
             for c in self._cuts],
            row_ids=[c["id"] for c in self._cuts])

    # ── retroalimentación ────────────────────────────────────────────────
    def _show(self, text: str, *, ok: bool) -> None:
        self.message.setText(text)
        self.message.setProperty("state", "success" if ok else "error")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setVisible(bool(text))

    def _apply(self, result: tuple[bool, str], done: str) -> None:
        ok, message = result
        self._show(done if ok else (message or "No se pudo completar."), ok=ok)
        if ok:
            self.refresh()

    def _need_species(self) -> str | None:
        species_id = self._species_id()
        if not species_id:
            MessageDialog.information(self, "Clasificación cárnica", "Elige una especie.")
        return species_id

    # ── especies ─────────────────────────────────────────────────────────
    def _new_species(self) -> None:
        dialog = CodeNameDialog("Nueva especie", parent=self,
                                suggest=catalog_suggester(self._presenter, "SPECIES"))
        if dialog.exec_():
            self._apply(self._meat.create_species(**dialog.values()), "Especie creada.")

    def _toggle_species(self) -> None:
        species_id = self._need_species()
        if not species_id:
            return
        row = next((s for s in self._species if s["id"] == species_id), {})
        self._apply(self._meat.set_species_active(species_id, not row.get("active")),
                    "Especie actualizada.")

    # ── regiones ─────────────────────────────────────────────────────────
    def _new_region(self) -> None:
        species_id = self._need_species()
        if not species_id:
            return
        dialog = CodeNameDialog(f"Nueva región — {self.species_combo.currentText()}",
                                parent=self, suggest=catalog_suggester(
                                    self._presenter, "ANATOMICAL_REGION",
                                    scope_id=species_id))
        if dialog.exec_():
            self._apply(self._meat.create_region(species_id=species_id, **dialog.values()),
                        "Región anatómica creada.")

    def _toggle_region(self) -> None:
        region_id = self.regions_table.selected_row_id()
        if not region_id:
            MessageDialog.information(self, "Regiones anatómicas", "Selecciona una región.")
            return
        row = next((r for r in self._regions if r["id"] == region_id), {})
        self._apply(self._meat.set_region_active(region_id, not row.get("active")),
                    "Región actualizada.")

    # ── cortes ───────────────────────────────────────────────────────────
    def _new_cut(self) -> None:
        species_id = self._need_species()
        if not species_id:
            return
        active_regions = [r for r in self._regions if r.get("active")]
        if not active_regions:
            MessageDialog.information(
                self, "Nuevo corte",
                "Esta especie no tiene regiones anatómicas activas. Crea primero la "
                "región (pestaña «Regiones anatómicas»).")
            return
        dialog = CutDialog(active_regions,
                           [c for c in self._cuts if c.get("status") == "ACTIVE"],
                           title=f"Nuevo corte — {self.species_combo.currentText()}",
                           parent=self, suggest=catalog_suggester(
                               self._presenter, "CUT", scope_id=species_id))
        if dialog.exec_():
            self._apply(self._meat.create_cut(species_id=species_id, **dialog.values()),
                        "Corte creado.")

    def _toggle_cut(self) -> None:
        cut_id = self.cuts_table.selected_row_id()
        if not cut_id:
            MessageDialog.information(self, "Cortes", "Selecciona un corte.")
            return
        row = next((c for c in self._cuts if c["id"] == cut_id), {})
        self._apply(self._meat.set_cut_active(cut_id, row.get("status") != "ACTIVE"),
                    "Corte actualizado.")


class CodeNameDialog(StandardDialog):
    """Nombre + código (especie, región anatómica); el código sale del nombre
    y es reescribible (PROD-23)."""

    def __init__(self, title: str, parent=None, *, suggest=None) -> None:
        super().__init__(parent, title=title)
        form = QFormLayout()
        self.code = StandardLineEdit(placeholder="Ej. PECHUGA")
        self.name = StandardLineEdit(placeholder="Nombre visible")
        form.addRow("Nombre *", self.name)
        form.addRow("Código", self.code)
        self._auto = AutoCodeBinder(self.name, self.code, suggest or (lambda _n: ""))
        self.content_layout().addLayout(form)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.content_layout().addWidget(self.error)
        box = self.add_button_box(ok_text="Guardar", on_accept=self._accept)
        box.button(QDialogButtonBox.Ok).setText("Guardar")

    def values(self) -> dict:
        return {"code": self._auto.code_for_save(), "name": self.name.text().strip()}

    def _accept(self) -> None:
        if not self.values()["name"]:
            self.error.setText("El nombre es obligatorio.")
            return
        self.accept()


class CutDialog(StandardDialog):
    def __init__(self, regions: list[dict], cuts: list[dict], *, title: str,
                 parent=None, suggest=None) -> None:
        super().__init__(parent, title=title)
        form = QFormLayout()
        self.code = StandardLineEdit(placeholder="Ej. PECHUGA_DESHUESADA")
        self.name = StandardLineEdit(placeholder="Nombre visible")
        self.region = self._combo([(r["id"], r["name"]) for r in regions])
        self.level = self._combo(list(CUT_LEVEL_ES.items()))
        self.bone = self._combo(list(BONE_STATUS_ES.items()), default="NOT_APPLICABLE")
        self.fat = self._combo(list(FAT_CLASS_ES.items()), default="NOT_APPLICABLE")
        self.grade = StandardLineEdit(placeholder="Opcional")
        self.parent_cut = self._combo([("", "(Ninguno)")] + [(c["id"], c["name"]) for c in cuts])
        self._auto = AutoCodeBinder(self.name, self.code, suggest or (lambda _n: ""))
        for label, widget in (("Nombre *", self.name), ("Código", self.code),
                              ("Región anatómica *", self.region), ("Nivel *", self.level),
                              ("Hueso", self.bone), ("Grasa", self.fat),
                              ("Grado de calidad", self.grade),
                              ("Corte padre", self.parent_cut)):
            form.addRow(label, widget)
        self.content_layout().addLayout(form)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.content_layout().addWidget(self.error)
        box = self.add_button_box(ok_text="Guardar", on_accept=self._accept)
        box.button(QDialogButtonBox.Ok).setText("Guardar")

    @staticmethod
    def _combo(items, default=None) -> QComboBox:
        combo = QComboBox()
        for value, label in items:
            combo.addItem(label, value)
        if default is not None:
            combo.setCurrentIndex(max(0, combo.findData(default)))
        return combo

    def values(self) -> dict:
        return {
            "code": self._auto.code_for_save(), "name": self.name.text().strip(),
            "anatomical_region_id": self.region.currentData(),
            "cut_level": self.level.currentData(), "bone_status": self.bone.currentData(),
            "fat_class": self.fat.currentData(),
            "quality_grade": self.grade.text().strip() or None,
            "parent_cut_id": self.parent_cut.currentData() or None,
        }

    def _accept(self) -> None:
        if not self.values()["name"]:
            self.error.setText("El nombre es obligatorio.")
            return
        self.accept()
