"""Oportunidades (§19-22, §85): directorio, pipeline (Kanban / tabla / resumen),
pronóstico, perdidas y detalle (CRM-43).

Antes: un directorio de lectura, sin alta, sin cambio de etapa, sin Kanban y
sin pronóstico, aunque los casos de uso y ``SalesPipelineForecastQueryService``
existían.

Toda transición pasa por su caso de uso: mover una tarjeta en el Kanban sólo
ABRE el formulario de cambio de etapa (§21).
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.application.crm.permissions import CRMPermissions
from frontend.desktop.components import (
    ColumnSpec,
    KPIBar,
    KPIDTO,
    PageHeader,
    SectionCard,
    StandardTable,
    StatusBadge,
    ViewState,
    create_secondary_button,
    create_state_widget,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.formatting import (
    fmt_date,
    fmt_datetime,
    fmt_money,
    fmt_percent,
)
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import label, options, variant
from frontend.desktop.modules.customers_crm.pages._kanban import (
    KanbanBoard,
    KanbanCard,
    KanbanColumn,
)
from frontend.desktop.modules.customers_crm.pages._pill_tab_bar import PillTabBar
from frontend.desktop.modules.customers_crm.pages._work_items import (
    WorkItemsPanel,
    new_activity,
    new_note,
    new_task,
)
from frontend.desktop.modules.customers_crm.pages._workbench import (
    Action,
    CrmWorkbenchPage,
    FilterSpec,
    Kpi,
    Row,
)
from frontend.desktop.themes.tokens import Spacing

_ACTIVE = ("OPEN", "ON_HOLD")
_CLOSED = ("WON", "LOST", "CANCELLED")


def _status(row: Row) -> str:
    return row.data.opportunity.status.value


def _stage_names(presenter) -> dict[str, str]:
    try:
        return {s.id: s.name for s in presenter.read("stages", include_inactive=True)}
    except Exception:  # noqa: BLE001
        return {}


def opportunity_cells(presenter, item, stage_names, customer_names) -> Row:
    o = item.opportunity
    follow = (fmt_datetime(item.next_activity_at) if item.next_activity_at
              else ("Sin actividad" if o.status.value in _ACTIVE else "—"))
    cells = [
        o.name, customer_names.get(o.customer_id, "—"), stage_names.get(o.stage_id, "—"),
        fmt_money(o.amount), fmt_percent(o.probability), fmt_money(o.weighted_value),
        fmt_date(o.expected_close_date), presenter.user_name(o.owner_user_id), follow,
        label("opportunity_status", o.status),
    ]
    detail = [
        ("Folio", str(o.code)), ("Oportunidad", o.name),
        ("Cliente", customer_names.get(o.customer_id, "—")),
        ("Etapa", stage_names.get(o.stage_id, "—")), ("Valor", fmt_money(o.amount)),
        ("Probabilidad", fmt_percent(o.probability)),
        ("Valor ponderado", fmt_money(o.weighted_value)),
        ("Cierre esperado", fmt_date(o.expected_close_date)),
        ("Propietario", presenter.user_name(o.owner_user_id)),
        ("Próxima actividad", follow), ("Días sin movimiento", str(item.days_idle)),
        ("Estado", label("opportunity_status", o.status)),
        ("Motivo de cierre", o.close_reason), ("Descripción", o.description),
    ]
    return Row(o.id, cells, item, detail, search_text=str(o.code))


# -- diálogos ----------------------------------------------------------------------
def create_opportunity_dialog(parent, presenter, *, customer_id: str | None = None,
                              customer_label: str = ""):
    stages = [(s.id, s.name) for s in presenter.read("stages") if not s.is_terminal()]
    return ask(parent, title="Nueva oportunidad", submit_text="Crear oportunidad", fields=(
        FieldSpec("customer_id", "Cliente", "customer", required=True, default=customer_id,
                  default_label=customer_label),
        FieldSpec("name", "Oportunidad", required=True,
                  placeholder="Ej. Surtido semanal restaurante"),
        FieldSpec("stage_id", "Etapa", "choice", options=tuple(stages),
                  default=stages[0][0] if stages else None),
        FieldSpec("owner_user_id", "Propietario", "user", default=presenter.current_user_id()),
        FieldSpec("amount", "Valor estimado", "money"),
        FieldSpec("probability", "Probabilidad (%)", "percent", default=0,
                  helper="Si la dejas en 0 se toma la de la etapa."),
        FieldSpec("expected_close_date", "Cierre esperado", "date"),
        FieldSpec("description", "Descripción", "textarea"),
    ), customer_provider=presenter.customer_search_options, user_options=presenter.users(),
        on_submit=lambda v: presenter.run(
            "create_opportunity", customer_id=v["customer_id"], name=v["name"],
            stage_id=v["stage_id"] or None, owner_user_id=v["owner_user_id"] or None,
            amount=v["amount"] or None, probability=v["probability"] or 0,
            expected_close_date=v["expected_close_date"], description=v["description"],
            origin_branch_id=presenter.branch_id()))


def move_stage_dialog(parent, presenter, opportunity, *, to_stage_id: str | None = None):
    stages = [s for s in presenter.read("stages")
              if not s.is_terminal() and s.id != opportunity.stage_id]
    default_stage = to_stage_id if any(s.id == to_stage_id for s in stages) else None
    probability = next((s.probability_default for s in stages if s.id == default_stage),
                       opportunity.probability)
    fields = [
        FieldSpec("to_stage_id", "Nueva etapa", "choice", required=True,
                  options=tuple((s.id, s.name) for s in stages), default=default_stage),
        FieldSpec("reason", "Motivo del cambio", "textarea"),
        FieldSpec("probability", "Probabilidad (%)", "percent", default=probability),
        FieldSpec("expected_close_date", "Cierre esperado", "date",
                  default=opportunity.expected_close_date),
    ]
    if presenter.can(CRMPermissions.OPPORTUNITIES_OVERRIDE_STAGE):
        fields.append(FieldSpec("override", "Forzar el cambio (omite requisitos de la etapa)",
                                "check"))
    return ask(parent, title=f"Mover etapa: {opportunity.name}", submit_text="Mover",
               intro="La etapa puede exigir campos, actividades previas o un motivo; si falta "
                     "algo, el cambio se rechaza y la oportunidad no se mueve.",
               fields=tuple(fields), on_submit=lambda v: presenter.run(
                   "move_opportunity_stage", opportunity_id=opportunity.id,
                   to_stage_id=v["to_stage_id"], reason=v["reason"],
                   probability=v["probability"], expected_close_date=v["expected_close_date"],
                   override=bool(v.get("override"))))


def _transition(parent, presenter, command: str, title: str, submit: str, record_id: str,
                *, reason_required: bool = True):
    return ask(parent, title=title, submit_text=submit, fields=(
        FieldSpec("reason", "Motivo", "textarea", required=reason_required),
    ), on_submit=lambda v: presenter.run(command, opportunity_id=record_id, reason=v["reason"]))


def edit_opportunity_dialog(parent, presenter, opportunity):
    return ask(parent, title="Editar oportunidad", submit_text="Guardar", fields=(
        FieldSpec("name", "Oportunidad", required=True, default=opportunity.name),
        FieldSpec("amount", "Valor estimado", "money", default=opportunity.amount),
        FieldSpec("description", "Descripción", "textarea", default=opportunity.description),
    ), on_submit=lambda v: presenter.run(
        "update_opportunity", opportunity_id=opportunity.id, name=v["name"],
        amount=v["amount"], description=v["description"]))


def product_interest_dialog(parent, presenter, opportunity_id: str):
    return ask(parent, title="Producto de interés", submit_text="Agregar", fields=(
        FieldSpec("product_name", "Producto", required=True),
        FieldSpec("quantity", "Cantidad", "integer", default=1, minimum=1),
        FieldSpec("estimated_unit_price", "Precio estimado", "money"),
        FieldSpec("notes", "Notas", "textarea"),
    ), on_submit=lambda v: presenter.run(
        "add_product_interest", opportunity_id=opportunity_id, product_name=v["product_name"],
        quantity=v["quantity"], estimated_unit_price=v["estimated_unit_price"] or None,
        notes=v["notes"]))


def opportunity_actions(page, presenter) -> list[Action]:
    p = presenter
    opp = lambda r: r.data.opportunity  # noqa: E731
    return [
        Action("Mover etapa", lambda r: page.report(move_stage_dialog(page, p, opp(r))),
               enabled=lambda r: _status(r) in _ACTIVE,
               permission=CRMPermissions.OPPORTUNITIES_CHANGE_STAGE, primary=True),
        Action("Ganada", lambda r: page.report(_transition(
            page, p, "win_opportunity", "Marcar como ganada", "Ganada", r.id,
            reason_required=False)), enabled=lambda r: _status(r) == "OPEN",
            permission=CRMPermissions.OPPORTUNITIES_MARK_WON),
        Action("Perdida", lambda r: page.report(_transition(
            page, p, "lose_opportunity", "Marcar como perdida", "Perdida", r.id)),
            enabled=lambda r: _status(r) in _ACTIVE,
            permission=CRMPermissions.OPPORTUNITIES_MARK_LOST),
        Action("Pausar", lambda r: page.report(_transition(
            page, p, "hold_opportunity", "Pausar oportunidad", "Pausar", r.id)),
            enabled=lambda r: _status(r) == "OPEN", permission=CRMPermissions.OPPORTUNITIES_EDIT),
        Action("Reanudar", lambda r: page.report(p.run("resume_opportunity",
                                                       opportunity_id=r.id)),
               enabled=lambda r: _status(r) == "ON_HOLD",
               permission=CRMPermissions.OPPORTUNITIES_EDIT),
        Action("Cancelar", lambda r: page.report(_transition(
            page, p, "cancel_opportunity", "Cancelar oportunidad", "Cancelar oportunidad", r.id)),
            enabled=lambda r: _status(r) in _ACTIVE, permission=CRMPermissions.OPPORTUNITIES_EDIT),
        Action("Reabrir", lambda r: page.report(_transition(
            page, p, "reopen_opportunity", "Reabrir oportunidad", "Reabrir", r.id)),
            enabled=lambda r: _status(r) in _CLOSED,
            permission=CRMPermissions.OPPORTUNITIES_REOPEN),
        Action("Asignar", lambda r: page.report(ask(
            page, title="Asignar propietario", submit_text="Asignar", fields=(
                FieldSpec("user", "Propietario", "user", required=True),),
            user_options=p.users(), on_submit=lambda v: p.run(
                "assign_opportunity", opportunity_id=r.id, assignee_user_id=v["user"]))),
            enabled=lambda r: _status(r) in _ACTIVE,
            permission=CRMPermissions.OPPORTUNITIES_ASSIGN),
        Action("Editar", lambda r: page.report(edit_opportunity_dialog(page, p, opp(r))),
               enabled=lambda r: _status(r) in _ACTIVE,
               permission=CRMPermissions.OPPORTUNITIES_EDIT),
        Action("Producto", lambda r: page.report(product_interest_dialog(page, p, r.id)),
               enabled=lambda r: _status(r) in _ACTIVE,
               permission=CRMPermissions.OPPORTUNITIES_EDIT,
               tooltip="Agregar un producto de interés"),
        Action("Actividad", lambda r: page.report(new_activity(page, p, "OPPORTUNITY", r.id)),
               permission=CRMPermissions.ACTIVITIES_CREATE),
    ]


# -- páginas -------------------------------------------------------------------------
class OpportunitiesPage(CrmWorkbenchPage):
    route_id = "crm.opportunities"
    title = "Oportunidades"
    subtitle = "Oportunidades comerciales en tu alcance."
    icon = Icons.SALES
    search_placeholder = "Buscar por oportunidad, cliente o folio…"
    empty_message = "No hay oportunidades en tu alcance. Crea una con «Nueva oportunidad»."
    show_detail = True
    detail_title = "Oportunidad"
    columns = (
        ColumnSpec("Oportunidad", stretch=True), ColumnSpec("Cliente"), ColumnSpec("Etapa"),
        ColumnSpec("Valor", "numeric"), ColumnSpec("Prob.", "numeric", min_width=60,
                                                   preferred_width=70),
        ColumnSpec("Ponderado", "numeric"), ColumnSpec("Cierre esperado", "date"),
        ColumnSpec("Propietario"), ColumnSpec("Próxima actividad", "date"),
        ColumnSpec("Estado", "status"),
    )
    statuses: tuple[str, ...] = _ACTIVE
    filters = (FilterSpec("status", "Abiertas y en pausa",
                          options=tuple(options("opportunity_status"))),)

    def page_actions(self):
        return [Action("Nueva oportunidad", lambda _r: self.report(
            create_opportunity_dialog(self, self._presenter)),
            permission=CRMPermissions.OPPORTUNITIES_CREATE, primary=True, needs_row=False)]

    def row_actions(self):
        return opportunity_actions(self, self._presenter)

    def fetch(self, filters):
        items = self._presenter.read("opportunity_rows")
        wanted = (filters.get("status"),) if filters.get("status") else self.statuses
        if wanted:
            items = [i for i in items if i.opportunity.status.value in wanted]
        stages = _stage_names(self._presenter)
        names = self._presenter.customer_names({i.opportunity.customer_id for i in items})
        return [opportunity_cells(self._presenter, i, stages, names) for i in items]

    def kpis(self, rows):
        if self.statuses != _ACTIVE:
            return None
        try:
            forecast = self._presenter.read("forecast")
        except Exception:  # noqa: BLE001 — sin permiso de pronóstico
            return None
        return [
            Kpi("Abiertas", str(forecast.open_count), "info"),
            Kpi("Pipeline", fmt_money(forecast.total_pipeline)),
            Kpi("Ponderado", fmt_money(forecast.weighted_pipeline), "accent"),
            Kpi("Vencidas", str(len(forecast.overdue)), "danger"),
            Kpi("Sin movimiento", str(len(forecast.stagnant)), "warning"),
        ]


class LostOpportunitiesPage(OpportunitiesPage):
    route_id = "crm.lost_opportunities"
    title = "Oportunidades perdidas"
    subtitle = "Perdidas y canceladas, con su motivo. Se pueden reabrir."
    statuses = ("LOST", "CANCELLED")
    empty_message = "No hay oportunidades perdidas."
    filters = ()

    def page_actions(self):
        return []


class PipelinePage(QWidget):
    """§21: Kanban, Tabla y Resumen del pipeline."""

    opportunity_opened = pyqtSignal(str)

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._loaded = False
        self.setObjectName("crmPipelinePage")
        self.setAccessibleName("Pipeline")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        actions = []
        if presenter.can(CRMPermissions.OPPORTUNITIES_CREATE):
            new = create_secondary_button(self, "Nueva oportunidad")
            new.clicked.connect(self._new)
            actions.append(new)
        self._move_btn = create_secondary_button(self, "Mover etapa")
        self._move_btn.setToolTip("Mueve la tarjeta seleccionada (alternativa a arrastrar).")
        self._move_btn.clicked.connect(self._move_selected)
        self._move_btn.setEnabled(False)
        if presenter.can(CRMPermissions.OPPORTUNITIES_CHANGE_STAGE):
            actions.append(self._move_btn)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        actions.append(refresh)
        root.addWidget(PageHeader(self, title="Pipeline", subtitle="Arrastra una tarjeta a otra "
                                  "etapa para proponer el cambio; se valida antes de aplicarse.",
                                  icon=Icons.ROUTE, compact=True, actions=actions))
        self._notice = QLabel("", self)
        self._notice.setWordWrap(True)
        self._notice.hide()
        root.addWidget(self._notice)
        self._kpis = KPIBar(self, cards=[])
        self._kpis.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        root.addWidget(self._kpis)
        self._tabs = PillTabBar(self)
        for key, text in (("board", "Tablero"), ("table", "Tabla"), ("summary", "Resumen")):
            self._tabs.add_tab(key, text)
        self._tabs.tab_changed.connect(self._show)
        root.addWidget(self._tabs)
        self._stack = QStackedWidget(self)
        self._board = KanbanBoard(self)
        self._board.move_requested.connect(self._on_drop)
        self._board.card_opened.connect(self.opportunity_opened.emit)
        self._board.selection_changed.connect(
            lambda cid: self._move_btn.setEnabled(bool(cid)))
        self._table_page = OpportunitiesPage(presenter, self)
        self._summary = StandardTable([ColumnSpec("Etapa", stretch=True),
                                       ColumnSpec("Oportunidades", "numeric"),
                                       ColumnSpec("Valor", "numeric"),
                                       ColumnSpec("Probabilidad", "numeric")], self)
        self._summary.setAccessibleName("Resumen por etapa")
        for widget in (self._board, self._table_page, self._summary):
            self._stack.addWidget(widget)
        root.addWidget(self._stack, stretch=1)
        self._items: dict[str, object] = {}
        self._table_page.row_opened.connect(self.opportunity_opened.emit)
        self._tabs.activate("board")

    def _show(self, key: str) -> None:
        self._stack.setCurrentIndex({"board": 0, "table": 1, "summary": 2}[key])
        if key == "table":
            self._table_page.ensure_loaded()

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            stages = self._presenter.read("stages")
            items = [i for i in self._presenter.read("opportunity_rows")
                     if i.opportunity.status.value in _ACTIVE]
        except Exception as exc:  # noqa: BLE001
            self._say(False, f"No fue posible cargar el pipeline: {exc}")
            return
        try:
            forecast = self._presenter.read("forecast")
        except Exception:  # noqa: BLE001 — sin permiso de pronóstico
            forecast = None
        by_stage = forecast.by_stage if forecast is not None else {}
        self._loaded = True
        self._items = {i.opportunity.id: i for i in items}
        names = self._presenter.customer_names({i.opportunity.customer_id for i in items})
        columns = []
        summary_rows = []
        for stage in stages:
            in_stage = [i for i in items if i.opportunity.stage_id == stage.id]
            if stage.is_terminal() and not in_stage:
                continue
            total = by_stage.get(stage.id)
            cards = tuple(KanbanCard(
                card_id=i.opportunity.id, title=i.opportunity.name,
                lines=(f"{names.get(i.opportunity.customer_id, '—')} · "
                       f"{fmt_money(i.opportunity.amount)} · {fmt_percent(i.opportunity.probability)}",
                       f"{self._presenter.user_name(i.opportunity.owner_user_id)} · próxima: "
                       f"{fmt_date(i.next_activity_at) if i.next_activity_at else 'sin actividad'}",
                       f"{i.days_idle} día(s) sin movimiento"
                       + (" · EN PAUSA" if i.opportunity.status.value == "ON_HOLD" else ""))
            ) for i in in_stage)
            columns.append(KanbanColumn(
                stage.id, stage.name,
                f"{len(in_stage)} oportunidad(es) · {fmt_money(total) if total else '$0.00'} · "
                f"{stage.probability_default}%", cards))
            summary_rows.append([stage.name, str(len(in_stage)), fmt_money(total or 0),
                                 f"{stage.probability_default}%"])
        self._board.set_columns(columns)
        self._summary.load_rows(summary_rows)
        self._move_btn.setEnabled(False)
        if forecast is not None:
            self._kpis.set_cards([
                KPIDTO(key="t", title="Pipeline total", value=fmt_money(forecast.total_pipeline)),
                KPIDTO(key="w", title="Ponderado", value=fmt_money(forecast.weighted_pipeline),
                       variant="accent"),
                KPIDTO(key="o", title="Abiertas", value=str(forecast.open_count)),
                KPIDTO(key="v", title="Vencidas", value=str(len(forecast.overdue)),
                       variant="danger"),
            ])
        else:
            self._kpis.set_cards([])
        if self._table_page._loaded:
            self._table_page.reload()

    def _say(self, ok: bool, message: str) -> None:
        self._notice.setProperty("state", "SUCCESS" if ok else "ERROR")
        self._notice.setText(message)
        self._notice.show()

    def _report(self, result) -> None:
        if result is None:
            return
        ok = bool(getattr(result, "success", False))
        self._say(ok, getattr(result, "message", "") or ("Listo." if ok else "Rechazado."))
        if ok:
            self.reload()

    def _new(self) -> None:
        self._report(create_opportunity_dialog(self, self._presenter))

    def _on_drop(self, opportunity_id: str, stage_id: str) -> None:
        item = self._items.get(opportunity_id)
        if item is None:
            return
        if not self._presenter.can(CRMPermissions.OPPORTUNITIES_CHANGE_STAGE):
            self._say(False, "No tienes permiso para cambiar la etapa.")
            return
        self._report(move_stage_dialog(self, self._presenter, item.opportunity,
                                       to_stage_id=stage_id))

    def _move_selected(self) -> None:
        card_id = self._board.selected_card_id()
        item = self._items.get(card_id) if card_id else None
        if item is not None:
            self._report(move_stage_dialog(self, self._presenter, item.opportunity))


class ForecastPage(QWidget):
    """§22: pronóstico operativo del pipeline (BI hace el avanzado)."""

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._loaded = False
        self.setObjectName("crmForecastPage")
        self.setAccessibleName("Pronóstico comercial")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        root.addWidget(PageHeader(self, title="Pronóstico comercial",
                                  subtitle="Pipeline total y ponderado de tus oportunidades "
                                           "abiertas.", icon=Icons.FORECAST, compact=True,
                                  actions=[refresh]))
        self._error = QLabel("", self)
        self._error.setProperty("state", "ERROR")
        self._error.setWordWrap(True)
        self._error.hide()
        root.addWidget(self._error)
        self._kpis = KPIBar(self, cards=[])
        self._kpis.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        root.addWidget(self._kpis)
        grid = QHBoxLayout()
        grid.setSpacing(Spacing.MD)
        self._by_stage = self._table(grid, "Por etapa", ("Etapa", "Valor"))
        self._closures = self._table(grid, "Cierres esperados", ("Oportunidad", "Cierre", "Valor"))
        root.addLayout(grid)
        grid2 = QHBoxLayout()
        grid2.setSpacing(Spacing.MD)
        self._overdue = self._table(grid2, "Vencidas (cierre ya pasó)",
                                    ("Oportunidad", "Cierre", "Valor"))
        self._stagnant = self._table(grid2, "Sin seguimiento (sin movimiento reciente)",
                                     ("Oportunidad", "Propietario", "Valor"))
        root.addLayout(grid2, stretch=1)

    def _table(self, layout, title: str, headers) -> StandardTable:
        card = SectionCard(self, title=title)
        table = StandardTable([ColumnSpec(h, "numeric" if h == "Valor" else "text")
                               for h in headers], card)
        table.setAccessibleName(title)
        card.add(table)
        layout.addWidget(card)
        return table

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            forecast = self._presenter.read("forecast")
            stages = _stage_names(self._presenter)
        except Exception as exc:  # noqa: BLE001
            self._error.setText(f"No fue posible calcular el pronóstico: {exc}")
            self._error.show()
            return
        self._error.hide()
        self._loaded = True
        self._kpis.set_cards([
            KPIDTO(key="t", title="Pipeline total", value=fmt_money(forecast.total_pipeline)),
            KPIDTO(key="w", title="Pipeline ponderado", value=fmt_money(forecast.weighted_pipeline),
                   variant="accent"),
            KPIDTO(key="o", title="Oportunidades abiertas", value=str(forecast.open_count)),
            KPIDTO(key="v", title="Vencidas", value=str(len(forecast.overdue)), variant="danger"),
            KPIDTO(key="s", title="Sin seguimiento", value=str(len(forecast.stagnant)),
                   variant="warning"),
        ])
        self._by_stage.load_rows([[stages.get(sid, "—"), fmt_money(v)]
                                  for sid, v in forecast.by_stage.items()])
        self._closures.load_rows([[o.name, fmt_date(o.expected_close_date), fmt_money(o.amount)]
                                  for o in forecast.expected_closures],
                                 row_ids=[o.id for o in forecast.expected_closures])
        self._overdue.load_rows([[o.name, fmt_date(o.expected_close_date), fmt_money(o.amount)]
                                 for o in forecast.overdue], row_ids=[o.id for o in forecast.overdue])
        self._stagnant.load_rows([[o.name, self._presenter.user_name(o.owner_user_id),
                                   fmt_money(o.amount)] for o in forecast.stagnant],
                                 row_ids=[o.id for o in forecast.stagnant])


class OpportunityDetailPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._opportunity_id: str | None = None
        self.setObjectName("crmOpportunityDetailPage")
        self.setAccessibleName("Detalle de oportunidad")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        self._header = PageHeader(self, title="Detalle de oportunidad", icon=Icons.DOCUMENT,
                                  compact=True, actions=[refresh])
        root.addWidget(self._header)
        badge_row = QHBoxLayout()
        self._badge = StatusBadge("—", self)
        badge_row.addWidget(self._badge)
        badge_row.addStretch(1)
        root.addLayout(badge_row)
        self._placeholder = create_state_widget(
            ViewState.EMPTY, self,
            message="Abre una oportunidad desde «Oportunidades» o el pipeline (doble clic).")
        root.addWidget(self._placeholder)
        self._body = QWidget(self)
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        facts_card = SectionCard(self._body, title="Datos")
        self._facts = QWidget(facts_card)
        self._facts_form = QFormLayout(self._facts)
        facts_card.add(self._facts)
        facts_card.body().addStretch(1)
        top.addWidget(facts_card)
        history_card = SectionCard(self._body, title="Historial de etapas")
        self._history = StandardTable([ColumnSpec("Fecha", "date"), ColumnSpec("De"),
                                       ColumnSpec("A"), ColumnSpec("Quién"),
                                       ColumnSpec("Motivo", stretch=True)], history_card)
        self._history.setAccessibleName("Historial de etapas")
        history_card.add(self._history)
        products_card = SectionCard(self._body, title="Productos de interés")
        self._products = StandardTable([ColumnSpec("Producto", stretch=True),
                                        ColumnSpec("Cantidad", "numeric"),
                                        ColumnSpec("Precio est.", "numeric")], products_card)
        self._products.setAccessibleName("Productos de interés")
        products_card.add(self._products)
        right = QVBoxLayout()
        right.addWidget(history_card)
        right.addWidget(products_card)
        top.addLayout(right)
        body.addLayout(top)
        follow = SectionCard(self._body, title="Seguimiento")
        self._work = WorkItemsPanel(presenter, follow)
        follow.add(self._work)
        body.addWidget(follow, stretch=1)
        root.addWidget(self._body, stretch=1)
        self._body.hide()
        self._error = QLabel("", self)
        self._error.setProperty("state", "ERROR")
        self._error.hide()
        root.addWidget(self._error)

    def ensure_loaded(self) -> None:
        pass

    def show_opportunity(self, opportunity_id: str) -> None:
        self._opportunity_id = opportunity_id
        self.reload()

    def reload(self) -> None:
        if not self._opportunity_id:
            return
        try:
            profile = self._presenter.read("opportunity_profile",
                                           opportunity_id=self._opportunity_id)
        except Exception as exc:  # noqa: BLE001
            self._error.setText(f"No fue posible abrir la oportunidad: {exc}")
            self._error.show()
            return
        self._error.hide()
        o = profile.opportunity
        stages = _stage_names(self._presenter)
        names = self._presenter.customer_names([o.customer_id])
        self._header.set_title(o.name)
        self._header.set_subtitle(f"{o.code} · {names.get(o.customer_id, '')}")
        self._badge.setText(label("opportunity_status", o.status))
        self._badge.set_status(variant("opportunity_status", o.status))

        class _Item:  # forma de OpportunityRow para reutilizar el detalle
            opportunity = o
            next_activity_at = None
            days_idle = 0

        while self._facts_form.rowCount():
            self._facts_form.removeRow(0)
        for caption, value in opportunity_cells(self._presenter, _Item, stages, names).detail:
            if caption in ("Próxima actividad", "Días sin movimiento"):
                continue
            text = QLabel(value or "—", self._facts)
            text.setWordWrap(True)
            self._facts_form.addRow(f"{caption}:", text)
        self._history.load_rows(
            [[fmt_datetime(h.created_at), stages.get(h.from_stage_id, "—"),
              stages.get(h.to_stage_id, "—"), self._presenter.user_name(h.changed_by_user_id),
              h.reason or "—"] for h in profile.stage_history],
            row_ids=[h.id for h in profile.stage_history])
        self._products.load_rows(
            [[pi.product_name, str(pi.quantity), fmt_money(pi.estimated_unit_price)]
             for pi in profile.product_interests],
            row_ids=[pi.id for pi in profile.product_interests])
        self._work.set_entity("OPPORTUNITY", o.id)
        self._placeholder.hide()
        self._body.show()


OPPORTUNITY_ROUTE_PAGES = {
    "crm.opportunities": OpportunitiesPage,
    "crm.lost_opportunities": LostOpportunitiesPage,
}
