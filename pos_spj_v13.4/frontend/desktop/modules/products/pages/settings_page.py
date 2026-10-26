"""Productos → Configuración (§45, PROD-22).

Tres bloques, cada uno con su permiso y su «Guardar»: valores por omisión de la
ficha, alertas a la campana (§35) y alertas por WhatsApp (§36). Los valores se
guardan en el catálogo gobernado (versionados y auditados). Es la única pantalla
que edita estos parámetros: Configuración general no los repite.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import PageHeader
from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.cards import SectionCard
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.modules.products.view_models import PRODUCT_TYPE_ES
from frontend.desktop.themes.tokens import Spacing


class ProductSettingsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productSettingsPage")
        self._presenter = presenter
        self._s = getattr(presenter, "settings", None)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.viewport = PageViewport(self)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(PageHeader(
            title="Configuración de Productos",
            subtitle="Valores por omisión, avisos de producto y mínimos de stock.",
            icon=getattr(Icons, "SETTINGS", None), compact=True))

        # ── valores por omisión ──────────────────────────────────────────
        defaults = SectionCard(self, title="Valores por omisión al dar de alta")
        form = QFormLayout()
        self.default_type = QComboBox()
        for code, label in sorted(PRODUCT_TYPE_ES.items(), key=lambda kv: kv[1]):
            self.default_type.addItem(label, code)
        self.default_unit = QComboBox()
        self.default_unit.addItem("(Sin preselección)", "")
        for unit in presenter.list_units():
            self.default_unit.addItem(f"{unit['code']} — {unit['name']}", unit["code"])
        self.default_tolerance = DecimalInput(precision=2, minimum="0", maximum="100")
        self.default_tolerance.setAccessibleName("Tolerancia de rendimiento por omisión")
        form.addRow("Tipo de producto", self.default_type)
        form.addRow("Unidad base", self.default_unit)
        form.addRow("Tolerancia de rendimiento (%)", self.default_tolerance)
        defaults.body().addLayout(form)
        self.btn_defaults = create_primary_button(self, "Guardar valores por omisión")
        self.btn_defaults.clicked.connect(self._save_defaults)
        defaults.body().addLayout(self._right(self.btn_defaults))
        layout.addWidget(defaults)

        # ── exigencias para activar ──────────────────────────────────────
        requirements = SectionCard(self, title="Exigencias para activar un producto")
        hint0 = QLabel("Además de las reglas fijas (unidad, categoría, especie en cárnicos), "
                       "estas exigencias impiden ACTIVAR un producto hasta completar el dato. "
                       "El borrador sí puede guardarse.")
        hint0.setProperty("role", "muted")
        hint0.setWordWrap(True)
        requirements.add(hint0)
        self.req_checks = {}
        for key, label in (
                ("meat_classification", "Clasificación cárnica (categoría o corte) en cárnicos"),
                ("shelf_life", "Vida útil en perecederos o con control de caducidad"),
                ("quality_profile", "Perfil de calidad en cárnicos"),
                ("catch_weight_range", "Rango de peso en productos de peso variable")):
            cb = QCheckBox(label)
            self.req_checks[key] = cb
            requirements.add(cb)
        self.btn_requirements = create_primary_button(self, "Guardar exigencias")
        self.btn_requirements.clicked.connect(self._save_requirements)
        requirements.body().addLayout(self._right(self.btn_requirements))
        layout.addWidget(requirements)

        # ── alertas a la campana ─────────────────────────────────────────
        alerts = SectionCard(self, title="Alertas a la campana")
        hint = QLabel("Al guardar un producto incompleto (sin categoría, cárnico sin especie, "
                      "perecedero sin vida útil…) o al alcanzar el mínimo de stock, se avisa "
                      "a los usuarios activos con estos roles en la sucursal correspondiente.")
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        alerts.add(hint)
        self.alerts_enabled = QCheckBox("Avisar por datos faltantes y stock bajo")
        alerts.add(self.alerts_enabled)
        roles_form = QFormLayout()
        self.alert_roles = StandardLineEdit(placeholder="almacenista,gerente")
        roles_form.addRow("Roles (separados por coma)", self.alert_roles)
        alerts.body().addLayout(roles_form)
        self.btn_alerts = create_primary_button(self, "Guardar alertas")
        self.btn_alerts.clicked.connect(self._save_alerts)
        alerts.body().addLayout(self._right(self.btn_alerts))
        layout.addWidget(alerts)

        # ── WhatsApp ─────────────────────────────────────────────────────
        whatsapp = SectionCard(self, title="Alertas de impacto y stock por WhatsApp")
        hint2 = QLabel("Los mínimos de stock y las alertas de alto impacto se encolan "
                       "para los teléfonos configurados. La cola reintenta cuando "
                       "el servicio está disponible; revisa los fallos en Notificaciones.")
        hint2.setProperty("role", "muted")
        hint2.setWordWrap(True)
        whatsapp.add(hint2)
        self.whatsapp_enabled = QCheckBox("Enviar por WhatsApp")
        whatsapp.add(self.whatsapp_enabled)
        phones_form = QFormLayout()
        self.whatsapp_phones = StandardLineEdit(placeholder="5215512345678, 5213398765432")
        phones_form.addRow("Teléfonos con lada", self.whatsapp_phones)
        whatsapp.body().addLayout(phones_form)
        self.btn_whatsapp = create_primary_button(self, "Guardar WhatsApp")
        self.btn_whatsapp.clicked.connect(self._save_whatsapp)
        whatsapp.body().addLayout(self._right(self.btn_whatsapp))
        layout.addWidget(whatsapp)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setProperty("role", "banner")
        self.message.hide()
        layout.addWidget(self.message)
        layout.addStretch(1)
        self.viewport.set_page(body)
        outer.addWidget(self.viewport)
        self.refresh()

    @staticmethod
    def _right(button) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        return row

    def refresh(self) -> None:
        if self._s is None:
            self._show(False, "La configuración de Productos no está disponible.")
            return
        s = self._s.current()
        self.default_type.setCurrentIndex(max(0, self.default_type.findData(
            s.default_product_type)))
        self.default_unit.setCurrentIndex(max(0, self.default_unit.findData(
            s.default_base_unit_code)))
        self.default_tolerance.set_decimal(s.default_yield_tolerance_pct)
        for key, attr in (("meat_classification", "require_meat_classification"),
                          ("shelf_life", "require_shelf_life"),
                          ("quality_profile", "require_quality_profile"),
                          ("catch_weight_range", "require_catch_weight_range")):
            self.req_checks[key].setChecked(bool(getattr(s, attr)))
        self.alerts_enabled.setChecked(s.alerts_enabled)
        self.alert_roles.setText(",".join(s.alert_roles))
        self.whatsapp_enabled.setChecked(s.whatsapp_enabled)
        self.whatsapp_phones.setText(", ".join(s.whatsapp_phones))
        for widgets, allowed in (
                ((self.default_type, self.default_unit, self.default_tolerance,
                  self.btn_defaults, self.btn_requirements, *self.req_checks.values()),
                 self._s.can_edit_defaults),
                ((self.alerts_enabled, self.alert_roles, self.btn_alerts),
                 self._s.can_edit_alerts),
                ((self.whatsapp_enabled, self.whatsapp_phones, self.btn_whatsapp),
                 self._s.can_edit_whatsapp)):
            for widget in widgets:
                widget.setEnabled(bool(allowed))

    def _show(self, ok: bool, text: str) -> None:
        self.message.setText(text)
        self.message.setProperty("state", "success" if ok else "error")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setVisible(bool(text))

    def _done(self, result: tuple[bool, str]) -> None:
        ok, message = result
        self._show(ok, message)
        if ok:
            self.refresh()

    def _save_defaults(self) -> None:
        if not self.default_tolerance.is_valid():
            self._show(False, "La tolerancia va de 0 a 100 %.")
            return
        self._done(self._s.save(defaults={
            "product_type": self.default_type.currentData(),
            "base_unit_code": self.default_unit.currentData(),
            "yield_tolerance_pct": str(self.default_tolerance.decimal_value() or 0)}))

    def _save_requirements(self) -> None:
        self._done(self._s.save(requirements={
            key: cb.isChecked() for key, cb in self.req_checks.items()}))

    def _save_alerts(self) -> None:
        self._done(self._s.save(alerts={"enabled": self.alerts_enabled.isChecked(),
                                        "roles": self.alert_roles.text()}))

    def _save_whatsapp(self) -> None:
        self._done(self._s.save(whatsapp={"enabled": self.whatsapp_enabled.isChecked(),
                                          "phones": self.whatsapp_phones.text()}))
