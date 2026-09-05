"""PriceRecommendationPage (§14/§32-40, BI-27) — "Decision Intelligence":
product+branch search + margin/vigencia inputs + "Generar recomendación"
action, rendering the KPI bar + evidence table
`PriceRecommendationPresenter` builds from a REAL `PricingIntelligenceService`
run, plus lifecycle action buttons that apply BI-18's real transition
functions to the in-memory recommendation (session-only — see the
presenter's own docstring for why there is no persistence yet).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    BranchSearchBox,
    ColumnSpec,
    IntegerInput,
    KPIBar,
    PageHeader,
    PercentInput,
    ProductSearchBox,
    StandardTable,
    create_danger_button,
    create_ghost_button,
    create_primary_button,
    create_success_button,
)
from frontend.desktop.modules.business_intelligence.presenters.price_recommendation_presenter import (
    RecommendationTransitionError,
    RecommendationUnavailableError,
    map_recommendation_kpis,
)


class PriceRecommendationPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Inteligencia de Negocios — Decision Intelligence")
        self.setAccessibleDescription(
            "Recomendaciones de precio con evidencia y ciclo de vida.")
        self._presenter = presenter
        self._loaded = False
        self._product_id: str | None = None
        self._branch_id: str | None = None
        self._recommendation = None

        root = QVBoxLayout(self)
        root.addWidget(PageHeader(
            title="Decision Intelligence",
            subtitle="Recomendaciones de precio con evidencia y ciclo de vida.",
            parent=self))

        form = QFormLayout()
        self.product = ProductSearchBox(parent=self, provider=self._presenter.search_products)
        self.product.selected.connect(self._select_product)
        form.addRow("Producto", self.product)
        self.branch = BranchSearchBox(parent=self, provider=self._presenter.search_branches)
        self.branch.selected.connect(self._select_branch)
        form.addRow("Sucursal", self.branch)
        self.margin_threshold = PercentInput(self)
        form.addRow("Umbral de margen bajo", self.margin_threshold)
        self.valid_for_days = IntegerInput(self, minimum=0, maximum=365)
        form.addRow("Vigencia (días)", self.valid_for_days)
        root.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch(1)
        generate = create_primary_button(self, "Generar recomendación")
        generate.clicked.connect(self.refresh)
        actions.addWidget(generate)
        root.addLayout(actions)

        self.message = QLabel("", self)
        self.message.setWordWrap(True)
        self.message.hide()
        root.addWidget(self.message)

        self.kpis = KPIBar(cards=[])
        root.addWidget(self.kpis)

        self.evidence_table = StandardTable([ColumnSpec("Campo"), ColumnSpec("Valor")], self)
        root.addWidget(self.evidence_table)

        lifecycle = QHBoxLayout()
        self.btn_acknowledge = create_ghost_button(self, "Reconocer")
        self.btn_start_review = create_ghost_button(self, "Iniciar revisión")
        self.btn_approve = create_success_button(self, "Aprobar")
        self.btn_reject = create_danger_button(self, "Rechazar")
        self.btn_dismiss = create_danger_button(self, "Descartar")
        for button, action in (
            (self.btn_acknowledge, "acknowledge"), (self.btn_start_review, "start_review"),
            (self.btn_approve, "approve"), (self.btn_reject, "reject"),
            (self.btn_dismiss, "dismiss"),
        ):
            button.clicked.connect(lambda _checked=False, a=action: self._apply_transition(a))
            lifecycle.addWidget(button)
        root.addLayout(lifecycle)

    def _select_product(self, option) -> None:
        self._product_id = option.id
        self.product.set_selected_label(option.label)

    def _select_branch(self, option) -> None:
        self._branch_id = option.id
        self.branch.set_selected_label(option.label)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.margin_threshold.setValue(self._presenter.default_margin_review_threshold_pct())
            self.valid_for_days.setValue(self._presenter.default_valid_for_days())
            self._loaded = True

    def refresh(self) -> None:
        try:
            recommendation, _price_rec, message = self._presenter.generate(
                product_id=self._product_id, branch_id=self._branch_id,
                margin_review_threshold_pct=self.margin_threshold.value(),
                valid_for_days=self.valid_for_days.value())
        except RecommendationUnavailableError as exc:
            QMessageBox.information(self, "Decision Intelligence", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - surface, never crash the page
            QMessageBox.warning(self, "Decision Intelligence", str(exc))
            return

        self._recommendation = recommendation
        if recommendation is None:
            self.message.setText(message or "")
            self.message.show()
            self.kpis.set_cards([])
            self.evidence_table.load_rows([])
            return

        self.message.hide()
        self.kpis.set_cards(map_recommendation_kpis(recommendation))
        self.evidence_table.load_rows(
            [[key, value] for key, value in recommendation.evidence.items()])

    def _apply_transition(self, action: str) -> None:
        if self._recommendation is None:
            QMessageBox.information(
                self, "Decision Intelligence", "Genera una recomendación primero.")
            return
        try:
            self._recommendation = self._presenter.apply_transition(self._recommendation, action)
        except RecommendationTransitionError as exc:
            QMessageBox.warning(self, "Decision Intelligence", str(exc))
            return
        self.kpis.set_cards(map_recommendation_kpis(self._recommendation))
