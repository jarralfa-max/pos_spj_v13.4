"""Página de trabajo canónica de Clientes y CRM (CRM-43).

Una sola estructura para todas las bandejas del módulo (§80):

    PageHeader (+ acciones de página)
    KPIBar opcional
    FilterBar: búsqueda + selectores declarados
    StandardTable  |  panel de detalle opcional
    barra de acciones sobre la fila seleccionada
    aviso en línea (éxito / rechazo)

Cada página declara columnas, filtros, ``fetch()`` y ``row_actions()``; la base
pinta, filtra, habilita cada acción según la fila elegida Y el permiso del
usuario (ocultar no es seguridad — el caso de uso revalida — pero ofrecer una
acción que se va a rechazar es peor) y recarga tras cada operación exitosa.

Antes de esta base el módulo tenía 4 directorios de sólo lectura y 53 rutas
«en construcción»; los casos de uso existían sin pantalla.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    ColumnSpec,
    KPIBar,
    KPIDTO,
    PageHeader,
    SearchableComboBox,
    SearchInput,
    SectionCard,
    StandardTable,
    ViewState,
    create_primary_button,
    create_secondary_button,
    create_state_widget,
)
from frontend.desktop.themes.tokens import Spacing


@dataclass
class Row:
    id: str
    cells: list[str]
    data: object = None
    #: Pares (etiqueta, valor) del panel de detalle.
    detail: list[tuple[str, str]] = field(default_factory=list)
    #: Texto libre para la búsqueda (además de las celdas).
    search_text: str = ""


@dataclass(frozen=True)
class FilterSpec:
    key: str
    placeholder: str
    options: tuple[tuple[str, str], ...] | Callable[[], list[tuple[str, str]]] = ()
    default: object = None


@dataclass(frozen=True)
class Action:
    label: str
    handler: Callable[[Row | None], None]
    #: ¿Aplica a la fila seleccionada? (estado del registro).
    enabled: Callable[[Row], bool] | None = None
    #: Código de permiso que exige (se consulta al presentador).
    permission: str | None = None
    primary: bool = False
    #: False → acción de página (no necesita fila; va en el encabezado).
    needs_row: bool = True
    tooltip: str = ""


@dataclass(frozen=True)
class Kpi:
    title: str
    value: str
    variant: str = "neutral"
    tooltip: str | None = None


class CrmWorkbenchPage(QWidget):
    row_opened = pyqtSignal(str)

    route_id: str = ""
    title: str = ""
    subtitle: str = ""
    icon: str | None = None
    columns: tuple[ColumnSpec, ...] = ()
    filters: tuple[FilterSpec, ...] = ()
    searchable: bool = True
    search_placeholder: str = "Buscar…"
    empty_message: str = "Sin registros"
    show_detail: bool = False
    detail_title: str = "Detalle"

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._rows: dict[str, Row] = {}
        self._loaded = False
        self.setObjectName("crmWorkbenchPage")
        self.setAccessibleName(self.title)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(Spacing.MD)

        self._actions = list(self.row_actions())
        page_buttons = []
        for action in self.page_actions():
            if not self._allowed(action):
                continue
            button = (create_primary_button if action.primary else create_secondary_button)(
                self, action.label)
            button.setAccessibleName(action.label)
            if action.tooltip:
                button.setToolTip(action.tooltip)
            button.clicked.connect(lambda _c=False, a=action: self._run(a, None))
            page_buttons.append(button)
        self.header = PageHeader(self, title=self.title, subtitle=self.subtitle, icon=self.icon,
                                 compact=True, actions=page_buttons)
        self._root.addWidget(self.header)

        self._notice = QLabel("", self)
        self._notice.setObjectName("crmWorkbenchNotice")
        self._notice.setWordWrap(True)
        self._notice.hide()
        self._root.addWidget(self._notice)

        # Se crea vacía AQUÍ (no en la primera carga): creada tarde, con el
        # ancho por defecto del widget, apilaba las tarjetas en una columna.
        self._kpi_bar = KPIBar(self, cards=[])
        self._kpi_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._kpi_bar.hide()
        self._root.addWidget(self._kpi_bar)

        self._build_before_table()

        self._filter_widgets: dict[str, SearchableComboBox] = {}
        if self.searchable or self.filters:
            row = QHBoxLayout()
            row.setSpacing(Spacing.SM)
            self._search = SearchInput(self, placeholder=self.search_placeholder)
            self._search.setAccessibleName(f"Buscar en {self.title}")
            self._search.search_changed.connect(lambda *_: self._apply_filters())
            if self.searchable:
                row.addWidget(self._search, stretch=1)
            for spec in self.filters:
                combo = SearchableComboBox(self, placeholder=spec.placeholder)
                combo.setAccessibleName(spec.placeholder)
                options = spec.options() if callable(spec.options) else list(spec.options)
                combo.set_options(options)
                if spec.default is not None:
                    combo.set_current_id(spec.default)
                combo.selection_changed.connect(lambda *_: self.reload())
                self._filter_widgets[spec.key] = combo
                row.addWidget(combo)
            self._root.addLayout(row)
        else:
            self._search = None

        self._stack = QStackedWidget(self)
        self._table = StandardTable(list(self.columns), self)
        self._table.setAccessibleName(f"Listado de {self.title}")
        self._table.doubleClicked.connect(lambda *_: self._open_selected())
        self._table.itemSelectionChanged.connect(self._selection_changed)
        self._empty = create_state_widget(ViewState.EMPTY, self, message=self.empty_message)
        self._stack.addWidget(self._table)
        self._stack.addWidget(self._empty)

        if self.show_detail:
            splitter = QSplitter(Qt.Horizontal, self)
            splitter.setObjectName("crmWorkbenchSplit")
            splitter.addWidget(self._stack)
            self._detail_card = SectionCard(self, title=self.detail_title)
            self._detail_body = QWidget(self._detail_card)
            self._detail_form = QFormLayout(self._detail_body)
            self._detail_form.setContentsMargins(0, 0, 0, 0)
            self._detail_card.add(self._detail_body)
            self._build_detail_extra(self._detail_card)
            self._detail_card.body().addStretch(1)
            splitter.addWidget(self._detail_card)
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 2)
            self._root.addWidget(splitter, stretch=1)
        else:
            self._root.addWidget(self._stack, stretch=1)

        self._action_buttons: list[tuple[Action, QWidget]] = []
        action_row = QHBoxLayout()
        action_row.setSpacing(Spacing.SM)
        for action in self._actions:
            if not self._allowed(action):
                continue
            button = (create_primary_button if action.primary else create_secondary_button)(
                self, action.label)
            button.setAccessibleName(action.label)
            if action.tooltip:
                button.setToolTip(action.tooltip)
            button.clicked.connect(lambda _c=False, a=action: self._run(a, self.selected_row()))
            action_row.addWidget(button)
            self._action_buttons.append((action, button))
        if self._action_buttons:
            action_row.addStretch(1)
            self._root.addLayout(action_row)
        self._selection_changed()

    # -- hooks -------------------------------------------------------------
    def page_actions(self) -> list[Action]:
        return []

    def row_actions(self) -> list[Action]:
        return []

    def fetch(self, filters: dict) -> list[Row]:
        raise NotImplementedError

    def kpis(self, rows: list[Row]) -> list[Kpi] | None:
        return None

    def open_row(self, row: Row) -> None:
        self.row_opened.emit(row.id)

    def _build_before_table(self) -> None:
        """Contenido opcional entre el aviso y los filtros."""

    def _build_detail_extra(self, card) -> None:
        """Contenido opcional bajo el detalle."""

    def on_selection(self, row: Row | None) -> None:
        """Gancho para paneles extra."""

    # -- ciclo de vida -----------------------------------------------------
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def filter_values(self) -> dict:
        return {key: combo.current_id() for key, combo in self._filter_widgets.items()}

    def reload(self) -> None:
        try:
            rows = list(self.fetch(self.filter_values()))
        except Exception as exc:  # noqa: BLE001 — una página siempre muestra algo
            self._rows = {}
            self._table.load_rows([], row_ids=[])
            self._stack.setCurrentWidget(self._empty)
            self.notify(False, f"No fue posible cargar {self.title.lower()}: {exc}")
            self._loaded = True
            return
        self._all_rows = rows
        self._apply_filters()
        kpis = self.kpis(rows)
        if kpis is not None:
            self._set_kpis(kpis)
        self._loaded = True

    def _apply_filters(self) -> None:
        rows = getattr(self, "_all_rows", [])
        needle = self._search.text().strip().lower() if self._search is not None else ""
        if needle:
            rows = [r for r in rows
                    if needle in (" ".join(r.cells) + " " + r.search_text).lower()]
        self._rows = {r.id: r for r in rows}
        self._table.load_rows([r.cells for r in rows], row_ids=[r.id for r in rows])
        self._stack.setCurrentWidget(self._table if rows else self._empty)
        self._selection_changed()

    def _set_kpis(self, kpis: list[Kpi]) -> None:
        cards = [KPIDTO(key=k.title, title=k.title, value=k.value, variant=k.variant,
                        tooltip=k.tooltip) for k in kpis]
        self._kpi_bar.set_cards(cards)
        self._kpi_bar.setVisible(bool(cards))

    # -- selección y acciones ------------------------------------------------
    def selected_row(self) -> Row | None:
        row_id = self._table.selected_row_id()
        return self._rows.get(row_id) if row_id else None

    def _allowed(self, action: Action) -> bool:
        if not action.permission:
            return True
        can = getattr(self._presenter, "can", None)
        return bool(callable(can) and can(action.permission))

    def _selection_changed(self) -> None:
        row = self.selected_row()
        for action, button in getattr(self, "_action_buttons", []):
            if not action.needs_row:
                button.setEnabled(True)
                continue
            button.setEnabled(row is not None and (action.enabled is None or action.enabled(row)))
        if self.show_detail:
            self._render_detail(row)
        self.on_selection(row)

    def _render_detail(self, row: Row | None) -> None:
        while self._detail_form.rowCount():
            self._detail_form.removeRow(0)
        if row is None:
            hint = QLabel("Selecciona un registro para ver su detalle.", self._detail_body)
            hint.setProperty("role", "muted")
            hint.setWordWrap(True)
            self._detail_form.addRow(hint)
            return
        for caption, value in row.detail:
            text = QLabel(value or "—", self._detail_body)
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._detail_form.addRow(f"{caption}:", text)

    def _open_selected(self) -> None:
        row = self.selected_row()
        if row is not None:
            self.open_row(row)

    def _run(self, action: Action, row: Row | None) -> None:
        if action.needs_row and row is None:
            return
        try:
            action.handler(row)
        except Exception as exc:  # noqa: BLE001 — la acción nunca tumba la página
            self.notify(False, f"{action.label}: {exc}")

    # -- avisos ----------------------------------------------------------------
    def notify(self, ok: bool, message: str) -> None:
        self._notice.setProperty("state", "SUCCESS" if ok else "ERROR")
        style = self._notice.style()
        if style is not None:
            style.unpolish(self._notice)
            style.polish(self._notice)
        self._notice.setText(message)
        self._notice.show()

    def report(self, result, *, success_message: str | None = None) -> bool:
        """Muestra el resultado de un caso de uso y recarga si fue exitoso.
        ``None`` = el usuario canceló: no se muestra nada."""
        if result is None:
            return False
        ok = bool(getattr(result, "success", False))
        message = getattr(result, "message", "") or ""
        self.notify(ok, (success_message or message) if ok else (message or "Operación rechazada."))
        if ok:
            self.reload()
        return ok
