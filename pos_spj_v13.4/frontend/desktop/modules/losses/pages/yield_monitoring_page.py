"""Página de Rendimientos (LOSS, PASS 6) — desviaciones y alertas abiertas.

Sólo presentación: todo llega por `YieldMonitoringPresenter`. Ni SQL ni
conexión, como el resto del módulo.

La ruta `losses_yields` abría un placeholder. No le faltaban datos:
`YieldMonitoringQueryService` ya existía y `losses_factory.py` ya lo construía.
"""
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QMessageBox

from frontend.desktop.components import (
    ColumnSpec,
    KPIBar,
    StandardPage,
    StandardTable,
    create_secondary_button,
)

_COLUMNAS_DESVIACION = [
    ColumnSpec(title="Producción", min_width=90),
    ColumnSpec(title="Producto", min_width=90),
    ColumnSpec(title="Esperado", kind="number", min_width=90),
    ColumnSpec(title="Real", kind="number", min_width=90),
    ColumnSpec(title="Diferencia", kind="number", min_width=100),
    ColumnSpec(title="Desviación", kind="number", min_width=100),
    ColumnSpec(title="Severidad", min_width=90),
    ColumnSpec(title="Detectada", min_width=130),
]

_COLUMNAS_ALERTA = [
    ColumnSpec(title="Severidad", min_width=90),
    ColumnSpec(title="Rendimiento esperado", kind="number", min_width=140),
    ColumnSpec(title="Rendimiento real", kind="number", min_width=130),
    ColumnSpec(title="Tolerancia", min_width=150),
    ColumnSpec(title="Mensaje", min_width=220, preferred_width=320, stretch=True),
    ColumnSpec(title="Abierta", min_width=130),
]


class YieldMonitoringPage(StandardPage):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(
            parent, title="Rendimientos",
            subtitle="Desviaciones entre lo esperado y lo producido, y las que superaron la tolerancia.",
        )
        self._presenter = presenter
        self._loaded = False
        self.setObjectName("lossesYieldMonitoringPage")
        self.setAccessibleName("Rendimientos de producción")

        root = self.content_layout

        acciones = QHBoxLayout()
        acciones.addStretch(1)
        actualizar = create_secondary_button(text="Actualizar")
        actualizar.clicked.connect(self.refresh)
        acciones.addWidget(actualizar)
        root.addLayout(acciones)

        self.kpis = KPIBar(cards=[])
        root.addWidget(self.kpis)

        root.addWidget(QLabel("Desviaciones recientes", self))
        self.variances = StandardTable(_COLUMNAS_DESVIACION, self)
        root.addWidget(self.variances, stretch=2)

        root.addWidget(QLabel("Alertas abiertas", self))
        self.alerts = StandardTable(_COLUMNAS_ALERTA, self)
        root.addWidget(self.alerts, stretch=1)

    def ensure_loaded(self) -> None:
        """Carga diferida: la pantalla consulta dos veces la base, y hacerlo al
        construir el módulo pagaría ese coste aunque nadie la abra."""
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self) -> None:
        try:
            desviaciones = self._presenter.variances()
            alertas = self._presenter.open_alerts()
        except Exception as exc:  # noqa: BLE001 — frontera de UI
            # Se avisa en vez de dejar las tablas con lo anterior: una pantalla
            # que no se actualiza y no lo dice es peor que una vacía.
            QMessageBox.warning(self, "Rendimientos", str(exc))
            return

        self.kpis.set_cards(self._presenter.kpi_cards(desviaciones, alertas))
        self.variances.load_rows(self._presenter.variance_rows(desviaciones))
        self.alerts.load_rows(self._presenter.alert_rows(alertas))
