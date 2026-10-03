"""Páginas de Tarjetas de fidelidad dentro de Fidelidad (LOY-29, §6, §30-51).

Las listas son páginas declarativas (`cards_catalog.py`). Tres pantallas tienen
forma propia:

* Resumen de tarjetas — conteos que entrega el backend.
* QR y validación — lo mismo que hace el POS al escanear (§49).
* Diseñador — editor declarativo de anverso y reverso con vista previa (§34-36).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.domain.loyalty_cards.enums import LoyaltyCardStatus
from frontend.desktop.components import FormField, KPIBar, KPIDTO, SearchableComboBox
from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.selection_controls import StandardCheckBox
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.components.pages import StandardPage
from frontend.desktop.modules.fidelidad.cards.cards_catalog import CARD_RECORD_ROUTES
from frontend.desktop.modules.fidelidad.records.labels import label_for
from frontend.desktop.modules.fidelidad.records.record_page import LoyaltyRecordPage
from frontend.desktop.modules.fidelidad.records.specs import RecordPageSpec
from frontend.desktop.modules.fidelidad.records.tabbed_page import LoyaltyTabbedRecordPage
from frontend.desktop.themes.tokens import Spacing


class CardsOverviewPage(StandardPage):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent, title="Resumen de tarjetas", subtitle="Tarjetas emitidas y producción en curso.")
        self.setObjectName("fidelidadCardsOverviewPage")
        self.setAccessibleName("Resumen de tarjetas")
        self._presenter = presenter
        self._loaded = False
        layout = self.content_layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)
        self.kpi_bar = KPIBar(cards=[])
        layout.addWidget(self.kpi_bar)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            datos = self._presenter.cards_overview() or {}
        except Exception as exc:  # visible, nunca silencioso
            self._status.setProperty("state", "ERROR")
            self._status.setText(f"No fue posible cargar el resumen: {exc}")
            self._status.show()
            return
        self._status.hide()
        self.kpi_bar.set_cards([
            KPIDTO(key="active", title="Activas", value=str(datos.get("active", 0)),
                   variant="primary"),
            KPIDTO(key="issued", title="Emitidas sin activar", value=str(datos.get("issued", 0))),
            KPIDTO(key="blocked", title="Bloqueadas", value=str(datos.get("blocked", 0))),
            KPIDTO(key="replaced", title="Repuestas", value=str(datos.get("replaced", 0))),
            KPIDTO(key="batches", title="Lotes por aprobar",
                   value=str(datos.get("batches_pending", 0)),
                   variant="warning" if datos.get("batches_pending") else "neutral"),
            KPIDTO(key="failed", title="Impresiones fallidas",
                   value=str(datos.get("print_failed", 0)),
                   variant="danger" if datos.get("print_failed") else "neutral"),
        ])
        self._loaded = True


class CardQrValidationPage(StandardPage):
    """Escanea o escribe lo que trae la tarjeta y muestra lo que vería el POS."""

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent, title="QR y validación", subtitle="El QR sólo lleva un token público; nunca ids internos ni datos personales.")
        self.setObjectName("fidelidadCardQrPage")
        self.setAccessibleName("QR y validación")
        self._presenter = presenter
        layout = self.content_layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)
        fila = QHBoxLayout()
        self.input = StandardLineEdit(self)
        self.input.setPlaceholderText("Escanea el QR o escribe el número de tarjeta")
        self.input.returnPressed.connect(self.validate)
        fila.addWidget(self.input, stretch=1)
        boton = create_primary_button(self, "Validar")
        boton.clicked.connect(self.validate)
        fila.addWidget(boton)
        layout.addLayout(fila)
        self.result = QLabel("", self)
        self.result.setObjectName("fidelidadCardQrResult")
        self.result.setWordWrap(True)
        layout.addWidget(self.result)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        self.input.setFocus()

    def validate(self) -> None:
        codigo = self.input.text().strip()
        if not codigo:
            self.result.setText("Escanea o escribe un código.")
            return
        resuelto = self._presenter.resolve_card(codigo)
        if resuelto is None or not resuelto.found:
            self.result.setProperty("state", "ERROR")
            self.result.setText("Tarjeta no registrada.")
            return
        estado = label_for(LoyaltyCardStatus, resuelto.card_status)
        lineas = [f"Tarjeta {resuelto.card_number} — {estado}"]
        if resuelto.program_name:
            lineas.append(f"Programa: {resuelto.program_name}")
        if resuelto.tier_name:
            lineas.append(f"Nivel: {resuelto.tier_name}")
        lineas.append("Puede usarse en caja." if resuelto.eligible else "NO puede usarse en caja.")
        lineas.extend(resuelto.warnings)
        self.result.setProperty("state", "READY" if resuelto.eligible else "WARNING")
        self.result.setText("\n".join(lineas))


_NAME_MODES = (("FULL_NAME", "Nombre completo"), ("FIRST_NAME", "Sólo el nombre"),
               ("INITIALS", "Iniciales"), ("NOT_PRINTED", "No imprimir el nombre"))


class CardSettingsPage(StandardPage):
    """§37: qué se imprime de una persona en su tarjeta. Por omisión NO se
    imprimen teléfono, correo, domicilio, saldo, puntos ni identificadores."""

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent, title="Configuración de tarjetas",
                         subtitle="Privacidad de lo impreso: nombre y puntos.")
        self.setObjectName("fidelidadCardSettingsPage")
        self._presenter = presenter
        self._loaded = False
        layout = self.content_layout
        self.notice = QLabel("", self)
        self.notice.setWordWrap(True)
        self.notice.hide()
        layout.addWidget(self.notice)
        self.name_mode = SearchableComboBox(self, placeholder="Cómo se imprime el nombre")
        self.name_mode.set_options(list(_NAME_MODES))
        layout.addWidget(FormField("Nombre en la tarjeta", self.name_mode, self))
        self.print_points = StandardCheckBox("Imprimir el saldo de puntos", self)
        layout.addWidget(self.print_points)
        aviso = QLabel("Nunca se imprimen teléfono, correo, domicilio ni identificadores "
                       "internos; el QR sólo lleva un token público.", self)
        aviso.setWordWrap(True)
        aviso.setProperty("role", "muted")
        layout.addWidget(aviso)
        self.save_button = create_primary_button(self, "Guardar")
        self.save_button.clicked.connect(self.save)
        self.save_button.setEnabled(presenter.can_edit_card_settings())
        layout.addWidget(self.save_button)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        ajustes = self._presenter.card_privacy_settings()
        if ajustes is not None:
            self.name_mode.set_current_id(ajustes.name_mode.value)
            self.print_points.setChecked(ajustes.print_points_balance)
        self._loaded = True

    def save(self) -> None:
        from backend.domain.loyalty_cards.policies.privacy_policy import CardNameMode

        modo = self.name_mode.current_id()
        if not modo:
            self._notify(False, "Elige cómo se imprime el nombre.")
            return
        resultado = self._presenter.run_command(
            "update_card_privacy", name_mode=CardNameMode(modo),
            print_points_balance=self.print_points.isChecked())
        self._notify(bool(resultado.success), resultado.message or "Guardado.")

    def _notify(self, ok: bool, mensaje: str) -> None:
        self.notice.setProperty("state", "SUCCESS" if ok else "WARNING")
        self.notice.setText(mensaje)
        self.notice.show()


def create_card_page(route_id: str, presenter, parent=None) -> QWidget:
    if route_id == "cards.overview":
        return CardsOverviewPage(presenter, parent)
    if route_id == "cards.qr":
        return CardQrValidationPage(presenter, parent)
    if route_id == "cards.settings":
        return CardSettingsPage(presenter, parent)
    if route_id == "cards.designer":
        from frontend.desktop.modules.fidelidad.cards.designer_page import CardDesignerPage
        return CardDesignerPage(presenter, parent)
    spec = CARD_RECORD_ROUTES[route_id]
    if isinstance(spec, RecordPageSpec):
        return LoyaltyRecordPage(presenter, spec, parent)
    return LoyaltyTabbedRecordPage(presenter, spec, parent)


__all__ = ["CardQrValidationPage", "CardSettingsPage", "CardsOverviewPage", "create_card_page"]
