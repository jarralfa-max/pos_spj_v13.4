"""FidelidadOverviewPage — el resumen del módulo (§64) y sus alertas.

Seis indicadores, como pide el prompt: miembros activos, puntos disponibles,
puntos por vencer, canjes del mes, cupones activos y saldo pendiente de vales.
La UI no calcula ninguno: los entrega `LoyaltyRecordsQueryService.overview()`
(derivados del libro con la política de dominio). Debajo, lo que espera que
alguien actúe, con un acceso directo a la pantalla donde se atiende.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import KPIBar, KPIDTO
from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.components.pages import StandardPage
from frontend.desktop.themes.tokens import Spacing


def _entero(valor: Decimal) -> str:
    return f"{int(valor):,}"


class FidelidadOverviewPage(StandardPage):
    def __init__(self, presenter, parent=None, *,
                 navigate: Callable[[str], None] | None = None) -> None:
        super().__init__(parent, title="Resumen", subtitle="Estado del programa de lealtad.")
        self.setObjectName("fidelidadOverviewPage")
        self.setAccessibleName("Resumen de Fidelidad")
        self._presenter = presenter
        self._navigate = navigate
        self._loaded = False

        self._layout = self.content_layout
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Spacing.MD)

        self._status = QLabel("", self)
        self._status.setObjectName("fidelidadOverviewStatus")
        self._status.setWordWrap(True)
        self._status.hide()
        self._layout.addWidget(self._status)

        self.kpi_bar = KPIBar(cards=[])
        self._layout.addWidget(self.kpi_bar)

        self._alerts_title = QLabel("Pendientes", self)
        self._alerts_title.setProperty("role", "sectionTitle")
        self._layout.addWidget(self._alerts_title)
        self._alerts_box = QVBoxLayout()
        self._alerts_box.setSpacing(Spacing.SM)
        self._layout.addLayout(self._alerts_box)
        self._layout.addStretch(1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            resumen = self._presenter.overview()
            alertas = self._presenter.alerts()
        except Exception as exc:  # la página siempre muestra algo; el motivo queda visible
            self._status.setProperty("state", "ERROR")
            self._status.setText(f"No fue posible cargar el resumen: {exc}")
            self._status.show()
            return
        self._status.hide()
        if resumen is not None:
            self.kpi_bar.set_cards([
                KPIDTO(key="members", title="Miembros activos",
                       value=_entero(Decimal(resumen.active_members)), variant="primary"),
                KPIDTO(key="points", title="Puntos disponibles",
                       value=_entero(resumen.available_points), variant="primary"),
                KPIDTO(key="expiring", title="Puntos por vencer",
                       value=_entero(resumen.expiring_points),
                       subtitle=f"próximos {resumen.expiring_window_days} días",
                       variant="warning" if resumen.expiring_points > 0 else "neutral"),
                KPIDTO(key="redemptions", title="Canjes del mes",
                       value=_entero(Decimal(resumen.redemptions_in_period))),
                KPIDTO(key="coupons", title="Cupones activos",
                       value=_entero(Decimal(resumen.active_coupons))),
                KPIDTO(key="vouchers", title="Saldo pendiente de vales",
                       value=f"$ {resumen.outstanding_voucher_balance:,.2f}"),
            ])
        self._render_alerts(alertas)
        self._loaded = True

    def _render_alerts(self, alertas: list) -> None:
        while self._alerts_box.count():
            item = self._alerts_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                while item.layout().count():
                    child = item.layout().takeAt(0).widget()
                    if child is not None:
                        child.deleteLater()
        if not alertas:
            self._alerts_box.addWidget(create_state_widget(
                ViewState.EMPTY, self, message="Nada pendiente."))
            return
        for alerta in alertas:
            fila = QHBoxLayout()
            texto = QLabel(f"{alerta.area}: {alerta.count} {alerta.message}", self)
            texto.setProperty("state", "ERROR" if alerta.severity == "danger" else "WARNING")
            texto.setWordWrap(True)
            fila.addWidget(texto, stretch=1)
            if self._navigate is not None:
                boton = create_secondary_button(self, "Abrir")
                boton.clicked.connect(lambda _=False, r=alerta.route_id: self._navigate(r))
                fila.addWidget(boton)
            self._alerts_box.addLayout(fila)


__all__ = ["FidelidadOverviewPage"]
