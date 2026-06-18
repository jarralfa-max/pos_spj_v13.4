# modulos/transferencias.py
# ── ModuloTransferencias — Two-Phase Enterprise Transfer UI ──────────────────
# Refactored per SPJ_REFACTOR_SKILL.md:
#   ✓ Cero SQL en UI  — toda consulta va por TransferQueryService
#   ✓ Cero commit/rollback en UI — toda mutación por Use Cases
#   ✓ SearchSelector en lugar de QComboBox para productos
#   ✓ new_uuid() (UUIDv7) para operation_id
#   ✓ ProductoRepository eliminado de la UI
#   ✓ _DBWrapper eliminado (era redundante con core.db.connection.wrap)
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.application.commands.transfer_commands import (
    CancelTransferCommand,
    DispatchTransferCommand,
    ReceiveTransferCommand,
    ReceiveTransferItem,
    TransferItem,
)
from backend.application.queries.transfer_query_service import TransferQueryService
from backend.application.use_cases.cancel_transfer_use_case import CancelTransferUseCase
from backend.application.use_cases.dispatch_transfer_use_case import DispatchTransferUseCase
from backend.application.use_cases.receive_transfer_use_case import ReceiveTransferUseCase
from backend.shared.ids import new_uuid
from core.events.event_bus import get_bus, EventBus
from frontend.desktop.components.search_selector import SearchOption, SearchSelector
from modulos.base import ModuloBase
from modulos.design_tokens import Colors, Spacing
from modulos.ui_components import (
    FilterBar,
    LoadingIndicator,
    EmptyStateWidget,
    PageHeader,
    Toast,
    confirm_action,
    create_card,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
    create_success_button,
)
from repositories.transferencias import (
    TransferAlreadyReceivedError,
    TransferError,
    TransferOverReceptionError,
    TransferRepository,
    TransferStockError,
)

logger = logging.getLogger("spj.ui.transferencias")

TRANSFER_DISPATCHED = "TRASPASO_INICIADO"
TRANSFER_RECEIVED   = "TRASPASO_CONFIRMADO"
TRANSFER_CANCELLED  = "TRASPASO_CANCELADO"

_C4 = Colors.SUCCESS_BASE
_C5 = Colors.DANGER_HOVER
_C6 = Colors.WARNING_HOVER
_C7 = Colors.ACCENT_BASE

_STATUS_COLORS = {
    "DISPATCHED": _C6,
    "RECEIVED":   _C4,
    "CANCELLED":  _C5,
    "PENDING":    Colors.PRIMARY_BASE,
}


class ModuloTransferencias(ModuloBase):
    def __init__(self, container, parent=None):
        db_conn = container.db if hasattr(container, "db") else container
        super().__init__(db_conn, parent)

        self.container       = container
        self.main_window     = parent
        self.sucursal_id     = 1
        self.sucursal_nombre = "Principal"
        self.usuario_actual  = "Sistema"
        self.rol_usuario     = ""

        from core.db.connection import wrap
        self.conexion = wrap(db_conn)
        self._repo      = TransferRepository(self.conexion)
        self._query_svc = TransferQueryService.from_connection(self.conexion)

        self._dispatch_uc = DispatchTransferUseCase(self._repo)
        self._receive_uc  = ReceiveTransferUseCase(self._repo)
        self._cancel_uc   = CancelTransferUseCase(self._repo)

        self._init_ui()
        self._subscribe_events()
        QTimer.singleShot(0, self._refresh_all)

    def set_sucursal(self, sucursal_id: int, sucursal_nombre: str) -> None:
        self.sucursal_id     = sucursal_id
        self.sucursal_nombre = sucursal_nombre
        if hasattr(self, "_recepcion_widget"):
            self._recepcion_widget.set_sucursal(sucursal_id, sucursal_nombre)
        QTimer.singleShot(0, self._refresh_all)

    def set_usuario_actual(self, usuario: str, rol: str) -> None:
        self.usuario_actual = usuario or "Sistema"
        self.rol_usuario    = rol or ""

    def obtener_usuario_actual(self) -> str:
        return self.usuario_actual

    # ── Events ────────────────────────────────────────────────────────────────

    def _subscribe_events(self) -> None:
        try:
            _bus = get_bus()
            for evt in (TRANSFER_DISPATCHED, TRANSFER_RECEIVED, TRANSFER_CANCELLED):
                _bus.subscribe(evt, self._on_data_changed)
        except Exception:
            pass

    def _on_data_changed(self, _data: dict) -> None:
        QTimer.singleShot(0, self._refresh_all)

    def _refresh_all(self) -> None:
        self._load_transfers()

    def limpiar(self) -> None:
        for evt in (TRANSFER_DISPATCHED, TRANSFER_RECEIVED, TRANSFER_CANCELLED):
            try:
                EventBus.unsubscribe(evt, self._on_data_changed)
            except Exception:
                pass

    # ── UI construction ───────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(Spacing.MD)

        hdr = QHBoxLayout()
        title = QLabel("Transferencias entre Sucursales")
        f = title.font(); f.setPointSize(15); f.setBold(True)
        title.setFont(f); title.setObjectName("heading")
        hdr.addWidget(title); hdr.addStretch()
        self._lbl_suc = QLabel()
        self._lbl_suc.setObjectName("textSecondary")
        hdr.addWidget(self._lbl_suc)
        root.addLayout(hdr)

        root.addWidget(self._crear_stats_bar())

        self._tabs            = QTabWidget()
        self._tab_transfers   = QWidget()
        self._tab_sugerencias = QWidget()
        self._tab_recepcion   = QWidget()
        self._tabs.addTab(self._tab_transfers,   "🔄 Transferencias")
        self._tabs.addTab(self._tab_sugerencias, "🔮 Sugerencias Inteligentes")
        self._tabs.addTab(self._tab_recepcion,   "📦 Recepción con QR")
        root.addWidget(self._tabs)

        self._build_tab_transfers(self._tab_transfers)
        self._build_tab_sugerencias(self._tab_sugerencias)
        self._build_tab_recepcion(self._tab_recepcion)

    def _crear_stats_bar(self) -> QWidget:
        """Stats bar — KPIs via TransferQueryService (sin SQL en UI)."""
        from PyQt5.QtWidgets import QFrame as _F, QHBoxLayout as _H, QVBoxLayout as _V
        bar = _F(); bar.setObjectName("statsBarTrf"); bar.setFixedHeight(64)
        bar.setStyleSheet(
            "QFrame#statsBarTrf{background:#1E293B;border-radius:8px;border:1px solid #334155;}"
        )
        lay = _H(bar); lay.setContentsMargins(20, 8, 20, 8); lay.setSpacing(0)

        # Read KPIs through the query service — no SQL in the UI
        try:
            kpi_data = self._query_svc.get_kpi_counts(branch_id=self.sucursal_id or None)
        except Exception:
            kpi_data = {}

        kpis = [
            ("Pendientes recepción", str(kpi_data.get("pending_reception", "—")), Colors.WARNING_BASE),
            ("Recibidas este mes",   str(kpi_data.get("received_month",    "—")), Colors.SUCCESS_BASE),
            ("En tránsito",          str(kpi_data.get("in_transit",        "—")), Colors.PRIMARY_BASE),
            ("Canceladas",           str(kpi_data.get("cancelled_month",   "—")), Colors.DANGER_BASE),
        ]

        for i, (lbl, val, col) in enumerate(kpis):
            if i > 0:
                sep = _F(); sep.setFrameShape(_F.VLine); sep.setFixedWidth(1)
                sep.setStyleSheet("background:#334155;border:none;")
                lay.addWidget(sep); lay.addSpacing(20)
            c = _V(); c.setSpacing(1)
            v = QLabel(val)
            v.setStyleSheet(f"color:{col};font-size:18px;font-weight:700;background:transparent;")
            l = QLabel(lbl.upper())
            l.setStyleSheet(
                "color:#64748B;font-size:9px;font-weight:700;letter-spacing:0.5px;background:transparent;"
            )
            c.addWidget(v); c.addWidget(l); lay.addLayout(c)
            if i < len(kpis) - 1:
                lay.addSpacing(20)
        lay.addStretch()
        return bar

    def _build_tab_transfers(self, parent_widget: QWidget) -> None:
        root = QVBoxLayout(parent_widget)
        root.setContentsMargins(0, 8, 0, 0); root.setSpacing(8)

        kpi_row = QHBoxLayout()
        self._kpi_pend = self._make_kpi("Pendientes de Recepción", "0", _C6)
        self._kpi_rec  = self._make_kpi("Recibidas (mes)",          "0", _C4)
        self._kpi_can  = self._make_kpi("Canceladas (mes)",         "0", _C5)
        for k in (self._kpi_pend, self._kpi_rec, self._kpi_can):
            kpi_row.addWidget(k)
        root.addLayout(kpi_row)

        fb = QHBoxLayout()
        self._filter_bar = FilterBar(
            self,
            placeholder="Buscar por ID o sucursal…",
            combo_filters={"estado": ["DISPATCHED", "RECEIVED", "CANCELLED", "PENDING"]},
        )
        self._filter_bar.filters_changed.connect(lambda _v: self._load_transfers())
        fb.addWidget(self._filter_bar, 1); fb.addStretch()
        btn_nueva = create_primary_button(self, "📤 Nueva Transferencia", "Crear nueva transferencia")
        btn_nueva.clicked.connect(self._nueva_transferencia)
        fb.addWidget(btn_nueva)
        root.addLayout(fb)

        self._loading = LoadingIndicator("Cargando transferencias…", self)
        self._loading.hide()
        root.addWidget(self._loading)

        self._tbl = QTableWidget()
        self._tbl.setColumnCount(9)
        self._tbl.setHorizontalHeaderLabels([
            "ID", "Origen", "Destino", "Estado",
            "Enviado por", "Recibido por", "Fecha Envío", "Fecha Recepción", "Diferencia",
        ])
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setAlternatingRowColors(True)
        hdr_ = self._tbl.horizontalHeader()
        for i in range(9):
            hdr_.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hdr_.setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl.itemSelectionChanged.connect(self._on_sel_changed)
        root.addWidget(self._tbl)

        self._empty_state = EmptyStateWidget(
            "Sin transferencias",
            "No hay transferencias para los filtros actuales.",
            "📭",
            self,
        )
        self._empty_state.hide()
        root.addWidget(self._empty_state)

        ab = QHBoxLayout()
        self._btn_recv   = create_success_button(self, "📥 Recepcionar",   "Confirmar recepción")
        self._btn_detail = create_secondary_button(self, "🔍 Ver Detalle", "Ver detalles")
        self._btn_cancel = create_danger_button(self, "❌ Cancelar",       "Cancelar transferencia")
        for b in (self._btn_recv, self._btn_detail, self._btn_cancel):
            b.setEnabled(False); ab.addWidget(b)
        ab.addStretch()
        self._btn_recv.clicked.connect(self._recepcionar)
        self._btn_detail.clicked.connect(self._ver_detalle)
        self._btn_cancel.clicked.connect(self._cancelar)
        root.addLayout(ab)

    def _make_kpi(self, title: str, value: str, color: str):
        from PyQt5.QtWidgets import QFrame
        card = create_card(self, padding=Spacing.SM, with_layout=False)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setFixedHeight(72)
        lay = QVBoxLayout(card); lay.setContentsMargins(10, 6, 10, 6)
        lt = QLabel(title); lt.setObjectName("caption")
        lv = QLabel(value)
        lv.setStyleSheet(f"color:{color};font-size:18px;font-weight:bold;")
        lay.addWidget(lt); lay.addWidget(lv)
        card._val_label = lv
        return card

    # ── Data loading (no SQL in module) ───────────────────────────────────────

    def _load_transfers(self, *_args) -> None:
        if hasattr(self, "_loading"):
            self._loading.show()
        try:
            filtros       = self._filter_bar.values() if hasattr(self, "_filter_bar") else {}
            status_filter = filtros.get("estado") or None
            search        = (filtros.get("search", "") or "").strip()

            rows = self._query_svc.list_transfers(
                branch_id=self.sucursal_id or None,
                status=status_filter,
                search=search,
            )

            if not hasattr(self, "_tbl"):
                return

            self._tbl.setRowCount(len(rows))
            if hasattr(self, "_empty_state"):
                self._empty_state.setVisible(len(rows) == 0)

            pend = rec = can = 0
            for ri, r in enumerate(rows):
                st = r.get("status", "")
                if st == "DISPATCHED": pend += 1
                elif st == "RECEIVED": rec += 1
                elif st == "CANCELLED": can += 1

                tid = str(r.get("id", ""))
                vals = [
                    tid[:8] + "…" if len(tid) > 8 else tid,
                    str(r.get("origin_name", r.get("branch_origin_id", "?"))),
                    str(r.get("dest_name",   r.get("branch_dest_id",   "?"))),
                    st,
                    str(r.get("dispatched_by", "—") or "—"),
                    str(r.get("received_by",   "—") or "—"),
                    str(r.get("created_at",    ""))[:16],
                    str(r.get("received_at",   ""))[:16] if r.get("received_at") else "—",
                    f"{float(r.get('difference_kg', 0)):.3f} kg",
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(str(v))
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if ci == 3:
                        it.setForeground(QColor(_STATUS_COLORS.get(st, Colors.NEUTRAL.SLATE_900)))
                        it.setTextAlignment(Qt.AlignCenter)
                    self._tbl.setItem(ri, ci, it)
                self._tbl.item(ri, 0).setData(Qt.UserRole, str(r.get("id", "")))

            if hasattr(self, "_kpi_pend"):
                self._kpi_pend._val_label.setText(str(pend))
            if hasattr(self, "_kpi_rec"):
                self._kpi_rec._val_label.setText(str(rec))
            if hasattr(self, "_kpi_can"):
                self._kpi_can._val_label.setText(str(can))
            if hasattr(self, "_lbl_suc"):
                self._lbl_suc.setText(f"Sucursal: {self.sucursal_nombre}")
        finally:
            if hasattr(self, "_loading"):
                self._loading.hide()

    # ── Selection helpers ──────────────────────────────────────────────────────

    def _on_sel_changed(self) -> None:
        tid = self._get_selected_id()
        has = bool(tid)
        if hasattr(self, "_btn_recv"):
            self._btn_recv.setEnabled(has)
        if hasattr(self, "_btn_detail"):
            self._btn_detail.setEnabled(has)
        if hasattr(self, "_btn_cancel"):
            self._btn_cancel.setEnabled(has)

    def _get_selected_id(self) -> Optional[str]:
        rows = self._tbl.selectedItems()
        if not rows:
            return None
        row = self._tbl.currentRow()
        item = self._tbl.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.UserRole) or item.text().rstrip("…")

    # ── Actions ────────────────────────────────────────────────────────────────

    def _nueva_transferencia(self) -> None:
        sucursales = self._query_svc.get_branches(exclude_branch_id=self.sucursal_id)
        if not sucursales:
            QMessageBox.warning(self, "Sin sucursales", "No hay otras sucursales activas."); return
        dlg = DialogoNuevaTransferencia(
            dispatch_uc=self._dispatch_uc,
            query_svc=self._query_svc,
            sucursales=sucursales,
            sucursal_id=self.sucursal_id,
            usuario=self.usuario_actual,
            parent=self,
        )
        if dlg.exec_() == QDialog.Accepted:
            self._refresh_all()

    def _recepcionar(self) -> None:
        tid = self._get_selected_id()
        if not tid:
            return
        try:
            transfer = self._repo.get_by_id(tid)
            if not transfer:
                QMessageBox.warning(self, "Error", "Transferencia no encontrada."); return
            if transfer.get("status") != "DISPATCHED":
                QMessageBox.warning(
                    self, "Error", "Solo se pueden recepcionar transferencias despachadas."
                ); return
            items = self._repo.get_items(tid)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc)); return
        dlg = DialogoRecepcion(
            receive_uc=self._receive_uc,
            transfer=transfer,
            items=items,
            usuario=self.usuario_actual,
            parent=self,
        )
        if dlg.exec_() == QDialog.Accepted:
            self._refresh_all()

    def _ver_detalle(self) -> None:
        tid = self._get_selected_id()
        if not tid:
            return
        try:
            transfer = self._repo.get_by_id(tid)
            items    = self._repo.get_items(tid)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc)); return
        dlg = DialogoDetalleTransfer(transfer, items, parent=self)
        dlg.exec_()

    def _cancelar(self) -> None:
        tid = self._get_selected_id()
        if not tid:
            return
        if not confirm_action(
            self,
            "Confirmar Cancelación",
            "¿Cancelar esta transferencia? Se restaurará el stock en origen.",
            confirm_text="Cancelar transferencia",
            cancel_text="Volver",
        ):
            return
        cmd = CancelTransferCommand(
            operation_id=new_uuid(),
            branch_id=str(self.sucursal_id),
            user_name=self.usuario_actual,
            transfer_id=tid,
        )
        try:
            result = self._cancel_uc.execute(cmd)
            if result.success:
                Toast.success(self, "Transferencia cancelada", "Stock restaurado en origen.")
                self._refresh_all()
            else:
                QMessageBox.warning(self, "Error", result.message)
        except TransferAlreadyReceivedError:
            QMessageBox.warning(self, "Error", "No se puede cancelar: ya fue recibida.")
        except TransferError as exc:
            QMessageBox.warning(self, "Error", str(exc))
        except Exception as exc:
            logger.exception("cancelar_transferencia")
            QMessageBox.critical(self, "Error Inesperado", str(exc))

    # ── Tab Sugerencias ────────────────────────────────────────────────────────

    def _build_tab_sugerencias(self, parent_widget: QWidget) -> None:
        lay = QVBoxLayout(parent_widget)
        lay.setContentsMargins(0, 8, 0, 0); lay.setSpacing(10)

        info_box = create_card(self, padding=Spacing.SM, with_layout=False)
        info_box.setStyleSheet(
            "QFrame{background:#eaf4fb;border:none;border-left:4px solid #3498db;"
            "border-radius:4px;padding:6px;}"
        )
        info_lay = QVBoxLayout(info_box); info_lay.setContentsMargins(10, 6, 10, 6)
        lbl_metodo = QLabel(
            "🧮 <b>Método:</b> Días de Suministro (DOS) + Coeficiente de Variación (CV) "
            "con Suavizado Exponencial de demanda (α=0.3) — últimos 30 días"
        )
        lbl_metodo.setWordWrap(True)
        lbl_metodo.setStyleSheet("color:#1a5276; font-size:12px;")
        info_lay.addWidget(lbl_metodo)
        lay.addWidget(info_box)

        params_box = QGroupBox("Parámetros de análisis")
        params_lay = QHBoxLayout(params_box)

        params_lay.addWidget(QLabel("DOS mínimo (días):"))
        self._spin_dos_min = QDoubleSpinBox()
        self._spin_dos_min.setRange(1, 30); self._spin_dos_min.setValue(0)
        self._spin_dos_min.setDecimals(0); self._spin_dos_min.setSuffix(" días")
        self._spin_dos_min.setToolTip(
            "Umbral mínimo de días de suministro. "
            "Sucursales con DOS menor a este valor se consideran en déficit."
        )
        params_lay.addWidget(self._spin_dos_min)

        params_lay.addWidget(QLabel("  CV umbral:"))
        self._spin_cv = QDoubleSpinBox()
        self._spin_cv.setRange(0.0, 1.0); self._spin_cv.setValue(0)
        self._spin_cv.setDecimals(2); self._spin_cv.setSingleStep(0.05)
        self._spin_cv.setToolTip(
            "Coeficiente de Variación mínimo para considerar un desequilibrio. "
            "0.40 = 40% de dispersión entre sucursales."
        )
        params_lay.addWidget(self._spin_cv)

        params_lay.addWidget(QLabel("  Ventana histórica:"))
        self._spin_window = QSpinBox()
        self._spin_window.setRange(7, 90); self._spin_window.setValue(0)
        self._spin_window.setSuffix(" días")
        self._spin_window.setToolTip("Días de historial de ventas para calcular velocidad.")
        params_lay.addWidget(self._spin_window)

        params_lay.addStretch()
        btn_analizar = QPushButton("🔍 Analizar Ahora")
        btn_analizar.setStyleSheet(
            f"background:{_C7};color:white;font-weight:bold;padding:6px 14px;border-radius:4px;"
        )
        btn_analizar.clicked.connect(self._ejecutar_analisis)
        params_lay.addWidget(btn_analizar)
        lay.addWidget(params_box)

        self._tbl_sug = QTableWidget()
        self._tbl_sug.setColumnCount(10)
        self._tbl_sug.setHorizontalHeaderLabels([
            "Urgencia", "Producto", "Origen → Destino",
            "Stock Origen", "DOS Origen",
            "Stock Destino", "DOS Destino",
            "Transferir", "CV", "Razón",
        ])
        self._tbl_sug.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_sug.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_sug.verticalHeader().setVisible(False)
        self._tbl_sug.setAlternatingRowColors(True)
        self._tbl_sug.setWordWrap(True)
        hdr_s = self._tbl_sug.horizontalHeader()
        hdr_s.setSectionResizeMode(9, QHeaderView.Stretch)
        for i in range(9):
            hdr_s.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl_sug.itemSelectionChanged.connect(self._on_sug_sel_changed)
        lay.addWidget(self._tbl_sug)

        ab = QHBoxLayout()
        self._lbl_sug_count = QLabel("Sin análisis — presiona 'Analizar Ahora'")
        self._lbl_sug_count.setStyleSheet("color:#7f8c8d; font-size:12px;")
        ab.addWidget(self._lbl_sug_count); ab.addStretch()
        self._btn_aplicar_sug = QPushButton("📤 Crear Transferencia desde Sugerencia")
        self._btn_aplicar_sug.setEnabled(False)
        self._btn_aplicar_sug.setStyleSheet(
            f"background:{_C4};color:white;font-weight:bold;padding:5px 12px;border-radius:4px;"
        )
        self._btn_aplicar_sug.clicked.connect(self._aplicar_sugerencia)
        ab.addWidget(self._btn_aplicar_sug)
        lay.addLayout(ab)
        self._sugerencias: list = []

    def _ejecutar_analisis(self) -> None:
        from core.services.transfer_suggestion_engine import TransferSuggestionEngine
        dos_min = self._spin_dos_min.value() or 5.0
        cv_thr  = self._spin_cv.value()      or 0.40
        window  = self._spin_window.value()   or 30
        try:
            engine = TransferSuggestionEngine(
                db=self.conexion,
                window_days=window,
                dos_min=dos_min,
                cv_threshold=cv_thr,
            )
            self._sugerencias = engine.analyze(limit=100)
            self._poblar_tabla_sugerencias(self._sugerencias)
        except Exception as exc:
            logger.exception("_ejecutar_analisis")
            QMessageBox.warning(self, "Error en análisis", str(exc))

    def _poblar_tabla_sugerencias(self, sugerencias: list) -> None:
        self._tbl_sug.setRowCount(len(sugerencias))
        for ri, s in enumerate(sugerencias):
            d = s.to_dict()
            score = d["urgency_score"]
            urgency_color = _C5 if score >= 80 else (_C6 if score >= 50 else _C4)
            vals = [
                f"{score:.0f}/100",
                d["product_name"],
                f"{d['origin_name']} → {d['dest_name']}",
                f"{d['origin_stock']:.2f} {d['product_unit']}",
                f"{d['origin_dos']:.0f} días",
                f"{d['dest_stock']:.2f} {d['product_unit']}",
                f"{d['dest_dos']:.0f} días",
                f"{d['qty_suggested']:.3f} {d['product_unit']}",
                f"{d['cv']:.2f}",
                d["reason"],
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 0:
                    it.setForeground(QColor(urgency_color))
                    it.setTextAlignment(Qt.AlignCenter)
                if ci in (3, 4, 5, 6, 7):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl_sug.setItem(ri, ci, it)

        total   = len(sugerencias)
        criticas = sum(1 for s in sugerencias if s.urgency_score >= 80)
        self._lbl_sug_count.setText(
            f"{total} sugerencias — {criticas} críticas (score ≥ 80)"
            if total
            else "Sin desequilibrios detectados con los parámetros actuales."
        )
        self._btn_aplicar_sug.setEnabled(False)

    def _on_sug_sel_changed(self) -> None:
        self._btn_aplicar_sug.setEnabled(self._tbl_sug.currentRow() >= 0)

    def _aplicar_sugerencia(self) -> None:
        row = self._tbl_sug.currentRow()
        if row < 0 or row >= len(self._sugerencias):
            return
        sug = self._sugerencias[row]
        d   = sug.to_dict()
        sucursales = self._query_svc.get_branches(exclude_branch_id=d["origin_branch_id"])
        dlg = DialogoNuevaTransferencia(
            dispatch_uc=self._dispatch_uc,
            query_svc=self._query_svc,
            sucursales=sucursales,
            sucursal_id=d["origin_branch_id"],
            usuario=self.usuario_actual,
            parent=self,
            preseed={
                "dest_branch_id": d["dest_branch_id"],
                "product_id":     d["product_id"],
                "qty":            d["qty_suggested"],
            },
        )
        if dlg.exec_() == QDialog.Accepted:
            self._refresh_all()
            self._tabs.setCurrentIndex(0)

    # ── Tab Recepción QR ──────────────────────────────────────────────────────

    def _build_tab_recepcion(self, parent_widget: QWidget) -> None:
        from modulos.recepcion_qr_widget import RecepcionQRWidget
        lay = QVBoxLayout(parent_widget); lay.setContentsMargins(0, 0, 0, 0)
        widget = RecepcionQRWidget(
            conexion=self.conexion,
            sucursal_id=self.sucursal_id,
            usuario=self.usuario_actual,
            parent=parent_widget,
        )
        self._recepcion_widget = widget
        lay.addWidget(widget)


# ── Dialogo Nueva Transferencia ───────────────────────────────────────────────

class DialogoNuevaTransferencia(QDialog):
    """Phase 1 Dispatch dialog.

    Uses SearchSelector (no QComboBox) for product selection per skill rule 20.
    Delegates persistence to DispatchTransferUseCase — no SQL in this dialog.
    """

    def __init__(
        self,
        dispatch_uc: DispatchTransferUseCase,
        query_svc: TransferQueryService,
        sucursales: List[Dict],
        sucursal_id: int,
        usuario: str,
        parent=None,
        preseed: Dict = None,
    ):
        super().__init__(parent)
        self._dispatch_uc = dispatch_uc
        self._query_svc   = query_svc
        self._sucursales  = sucursales
        self._sucursal_id = sucursal_id
        self._usuario     = usuario
        self._preseed     = preseed or {}
        self._items: List[Dict] = []
        self._selected_product: Optional[Dict] = None

        self.setWindowTitle("Nueva Transferencia — Fase 1: Despacho")
        self.setMinimumWidth(720); self.setMinimumHeight(560)
        self._productos = query_svc.list_products_for_dispatch(sucursal_id)
        self._build_ui()
        self._apply_preseed()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)

        fl = QFormLayout()
        self._combo_dest = QComboBox()
        for s in self._sucursales:
            self._combo_dest.addItem(s["nombre"], s["id"])
        self._combo_origin_type = QComboBox()
        self._combo_origin_type.addItems(["BRANCH", "GLOBAL"])
        self._combo_dest_type = QComboBox()
        self._combo_dest_type.addItems(["BRANCH", "GLOBAL"])
        self._e_delivered_by = QLineEdit(); self._e_delivered_by.setText(self._usuario)
        self._e_obs = QTextEdit(); self._e_obs.setMaximumHeight(60)
        self._e_obs.setPlaceholderText("Observaciones (opcional)…")
        fl.addRow("Sucursal Destino*:",  self._combo_dest)
        fl.addRow("Tipo Origen:",        self._combo_origin_type)
        fl.addRow("Tipo Destino:",       self._combo_dest_type)
        fl.addRow("Entregado por*:",     self._e_delivered_by)
        fl.addRow("Observaciones:",      self._e_obs)
        lay.addLayout(fl)

        grp = QGroupBox("Productos a Transferir")
        gl  = QVBoxLayout(grp)

        self._tbl_items = QTableWidget()
        self._tbl_items.setColumnCount(4)
        self._tbl_items.setHorizontalHeaderLabels(["Producto", "Cantidad", "Unidad", "Stock Actual"])
        self._tbl_items.verticalHeader().setVisible(False)
        hdr = self._tbl_items.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        gl.addWidget(self._tbl_items)

        # ── SearchSelector (regla 20) en lugar de QComboBox para productos ──
        sel_row = QHBoxLayout()
        def _product_provider(query: str) -> List[SearchOption]:
            q = query.strip().lower()
            return [
                SearchOption(
                    id=str(p["id"]),
                    label=p["nombre"],
                    subtitle=f"stock: {p['existencia']:.3f} {p['unidad']}",
                )
                for p in self._productos
                if not q or q in p["nombre"].lower()
            ][:50]

        self._product_selector = SearchSelector(
            parent=self,
            provider=_product_provider,
            placeholder="Buscar producto por nombre…",
        )
        self._product_selector.setMinimumWidth(300)
        self._product_selector.setMaximumHeight(120)
        self._product_selector.selected.connect(self._on_product_selected)

        self._spin_qty = QDoubleSpinBox()
        self._spin_qty.setRange(0.0, 999999.0)
        self._spin_qty.setDecimals(3)
        self._spin_qty.setValue(0.0)  # empieza en cero (regla 22)

        btn_add = QPushButton("➕ Agregar")
        btn_add.setStyleSheet(
            f"background:{Colors.PRIMARY_BASE};color:white;padding:4px 10px;border-radius:3px;"
        )
        btn_add.clicked.connect(self._add_item)
        btn_del = QPushButton("🗑 Quitar"); btn_del.clicked.connect(self._remove_item)

        sel_row.addWidget(QLabel("Buscar:"), 0)
        sel_row.addWidget(self._product_selector, 2)
        sel_row.addWidget(QLabel("Cant:"), 0)
        sel_row.addWidget(self._spin_qty, 1)
        sel_row.addWidget(btn_add, 0)
        sel_row.addWidget(btn_del, 0)
        gl.addLayout(sel_row)
        lay.addWidget(grp)

        bl = QHBoxLayout()
        btn_ok = QPushButton("📤 Despachar Transferencia")
        btn_ok.setObjectName("primaryBtn"); btn_ok.clicked.connect(self._despachar)
        btn_no = QPushButton("Cancelar")
        btn_no.setObjectName("secondaryBtn"); btn_no.clicked.connect(self.reject)
        bl.addStretch(); bl.addWidget(btn_ok); bl.addWidget(btn_no)
        lay.addLayout(bl)

    def _on_product_selected(self, option: SearchOption) -> None:
        pid = int(option.id) if option.id.isdigit() else option.id
        self._selected_product = next(
            (p for p in self._productos if str(p["id"]) == str(pid)), None
        )

    def _apply_preseed(self) -> None:
        if not self._preseed:
            return
        dest_id = self._preseed.get("dest_branch_id")
        if dest_id:
            for i in range(self._combo_dest.count()):
                if self._combo_dest.itemData(i) == dest_id:
                    self._combo_dest.setCurrentIndex(i); break
        prod_id = self._preseed.get("product_id")
        qty     = float(self._preseed.get("qty", 0))
        if prod_id and qty > 0:
            prod = next((p for p in self._productos if str(p["id"]) == str(prod_id)), None)
            if prod:
                self._selected_product = prod
                self._product_selector.set_selected_label(prod["nombre"])
                self._spin_qty.setValue(qty)
                self._add_item()

    def _add_item(self) -> None:
        prod = self._selected_product
        if not prod:
            QMessageBox.warning(self, "Validación", "Seleccione un producto de la lista."); return
        qty = self._spin_qty.value()
        if qty <= 0:
            QMessageBox.warning(self, "Validación", "Cantidad debe ser mayor a 0."); return
        pid = prod["id"]
        if any(str(i["product_id"]) == str(pid) for i in self._items):
            QMessageBox.warning(self, "Duplicado", "Este producto ya está en la lista."); return
        ex = float(prod.get("existencia", 0))
        if qty > ex:
            QMessageBox.warning(
                self, "Stock Insuficiente",
                f"Stock disponible: {ex:.3f} {prod.get('unidad','kg')}. "
                f"Solicitado: {qty:.3f}.",
            ); return
        self._items.append({
            "product_id": pid,
            "quantity":   qty,
            "unit":       prod.get("unidad", "kg"),
            "nombre":     prod["nombre"],
            "stock":      ex,
        })
        self._refresh_items_table()
        self._product_selector.clear()
        self._selected_product = None
        self._spin_qty.setValue(0.0)

    def _remove_item(self) -> None:
        row = self._tbl_items.currentRow()
        if row >= 0:
            self._items.pop(row); self._refresh_items_table()

    def _refresh_items_table(self) -> None:
        self._tbl_items.setRowCount(len(self._items))
        for ri, item in enumerate(self._items):
            for ci, v in enumerate([
                item["nombre"],
                f"{item['quantity']:.3f}",
                item["unit"],
                f"{item['stock']:.3f}",
            ]):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci > 0:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl_items.setItem(ri, ci, it)

    def _despachar(self) -> None:
        dest_id = self._combo_dest.currentData()
        if not dest_id:
            QMessageBox.warning(self, "Validación", "Seleccione sucursal destino."); return
        delivered_by = self._e_delivered_by.text().strip()
        if not delivered_by:
            QMessageBox.warning(self, "Validación", "Indique quién entrega."); return
        if not self._items:
            QMessageBox.warning(self, "Validación", "Agregue al menos un producto."); return

        cmd = DispatchTransferCommand(
            operation_id=new_uuid(),
            branch_id=str(self._sucursal_id),
            user_name=delivered_by,
            origin_branch_id=self._sucursal_id,
            dest_branch_id=int(dest_id),
            items=tuple(
                TransferItem(
                    product_id=i["product_id"],
                    quantity_sent=i["quantity"],
                    unit=i.get("unit", "kg"),
                )
                for i in self._items
            ),
            dispatched_by=delivered_by,
            origin_type=self._combo_origin_type.currentText(),
            destination_type=self._combo_dest_type.currentText(),
            observations=self._e_obs.toPlainText().strip(),
        )
        try:
            result = self._dispatch_uc.execute(cmd)
            if result.success:
                Toast.success(
                    self.parent() or self,
                    f"Transferencia {str(result.entity_id or '')[:8]}… despachada",
                    "En espera de recepción en sucursal destino.",
                )
                self.accept()
            else:
                QMessageBox.warning(self, "Error", result.message)
        except TransferStockError as exc:
            QMessageBox.warning(self, "Stock Insuficiente", str(exc))
        except TransferError as exc:
            QMessageBox.warning(self, "Error", str(exc))
        except Exception as exc:
            logger.exception("despachar_transferencia")
            QMessageBox.critical(self, "Error Inesperado", str(exc))


# ── Dialogo Recepción ─────────────────────────────────────────────────────────

class DialogoRecepcion(QDialog):
    """Phase 2 Reception dialog — no SQL, delegates to ReceiveTransferUseCase."""

    def __init__(
        self,
        receive_uc: ReceiveTransferUseCase,
        transfer: Dict,
        items: List[Dict],
        usuario: str,
        parent=None,
    ):
        super().__init__(parent)
        self._receive_uc = receive_uc
        self._transfer   = transfer
        self._items      = items
        self._usuario    = usuario
        self.setWindowTitle(f"Recepción — Transferencia {str(transfer.get('id',''))[:8]}…")
        self.setMinimumWidth(680); self.setMinimumHeight(500)
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)

        info = QGroupBox("Información del Despacho")
        il = QFormLayout(info)
        il.addRow("ID:",              QLabel(str(self._transfer.get("id", ""))))
        il.addRow("Enviado por:",     QLabel(str(self._transfer.get("delivered_by", "—"))))
        il.addRow("Fecha despacho:",  QLabel(str(self._transfer.get("created_at", ""))[:16]))
        il.addRow("Origen:",          QLabel(str(
            self._transfer.get("origin_name", self._transfer.get("branch_origin_id", "?"))
        )))
        lay.addWidget(info)

        grp = QGroupBox("Productos — Ingrese cantidades recibidas")
        gl  = QVBoxLayout(grp)
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(6)
        self._tbl.setHorizontalHeaderLabels(
            ["Producto", "Enviado", "Unidad", "Recibido", "Diferencia", "Observación"]
        )
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setAlternatingRowColors(True)
        hdr = self._tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4, 5):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl.setRowCount(len(self._items))
        for ri, item in enumerate(self._items):
            qty_sent = float(item.get("quantity_sent", item.get("quantity", 0)))
            prod_it  = QTableWidgetItem(item.get("product_nombre", item.get("nombre", "?")))
            prod_it.setFlags(Qt.ItemIsEnabled)
            sent_it = QTableWidgetItem(f"{qty_sent:.3f}")
            sent_it.setFlags(Qt.ItemIsEnabled)
            sent_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            unit_it = QTableWidgetItem(item.get("unit", "kg"))
            unit_it.setFlags(Qt.ItemIsEnabled)
            recv_spin = QDoubleSpinBox()
            recv_spin.setRange(0.0, qty_sent); recv_spin.setDecimals(3)
            recv_spin.setValue(qty_sent)  # sensible default: todo recibido
            recv_spin.setProperty("row", ri)
            recv_spin.setProperty("qty_sent", qty_sent)
            recv_spin.valueChanged.connect(self._update_difference)
            diff_it = QTableWidgetItem("0.000")
            diff_it.setFlags(Qt.ItemIsEnabled)
            diff_it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            obs_it = QTableWidgetItem("")
            self._tbl.setItem(ri, 0, prod_it)
            self._tbl.setItem(ri, 1, sent_it)
            self._tbl.setItem(ri, 2, unit_it)
            self._tbl.setCellWidget(ri, 3, recv_spin)
            self._tbl.setItem(ri, 4, diff_it)
            self._tbl.setItem(ri, 5, obs_it)
        gl.addWidget(self._tbl)
        lay.addWidget(grp)

        rf = QFormLayout()
        self._e_recv_by = QLineEdit(); self._e_recv_by.setText(self._usuario)
        self._e_obs     = QTextEdit(); self._e_obs.setMaximumHeight(60)
        self._e_obs.setPlaceholderText("Observaciones de recepción…")
        rf.addRow("Recibido por*:", self._e_recv_by)
        rf.addRow("Observaciones:", self._e_obs)
        lay.addLayout(rf)

        self._lbl_diff = QLabel("Diferencia total: 0.000 kg")
        self._lbl_diff.setStyleSheet("font-size:13px;font-weight:bold;")
        lay.addWidget(self._lbl_diff)

        bl = QHBoxLayout()
        btn_ok = QPushButton("✅ Confirmar Recepción")
        btn_ok.setObjectName("successBtn"); btn_ok.clicked.connect(self._confirmar)
        btn_no = QPushButton("Cancelar")
        btn_no.setObjectName("secondaryBtn"); btn_no.clicked.connect(self.reject)
        bl.addStretch(); bl.addWidget(btn_ok); bl.addWidget(btn_no)
        lay.addLayout(bl)

    def _update_difference(self) -> None:
        total_diff = 0.0
        for ri in range(self._tbl.rowCount()):
            spin    = self._tbl.cellWidget(ri, 3)
            sent_it = self._tbl.item(ri, 1)
            if not spin or not sent_it:
                continue
            qty_sent = float(sent_it.text())
            qty_recv = spin.value()
            diff = qty_recv - qty_sent
            total_diff += abs(diff)
            diff_it = self._tbl.item(ri, 4)
            if diff_it:
                diff_it.setText(f"{diff:.3f}")
                diff_it.setForeground(QColor(_C5 if diff < -0.001 else _C4))
        self._lbl_diff.setText(f"Diferencia total: {total_diff:.3f} kg")
        color = _C5 if total_diff > 0.01 else _C4
        self._lbl_diff.setStyleSheet(f"font-size:13px;font-weight:bold;color:{color};")

    def _confirmar(self) -> None:
        recv_by = self._e_recv_by.text().strip()
        if not recv_by:
            QMessageBox.warning(self, "Validación", "Ingrese quién recibe."); return

        received_items: List[ReceiveTransferItem] = []
        for ri, item in enumerate(self._items):
            spin = self._tbl.cellWidget(ri, 3)
            if not spin:
                continue
            product_id = item.get("product_id")
            qty_recv   = spin.value()
            qty_sent   = float(item.get("quantity_sent", item.get("quantity", 0)))
            if qty_recv > qty_sent + 0.001:
                prod_name = item.get("product_nombre", item.get("nombre", "?"))
                QMessageBox.warning(
                    self, "Error de Recepción",
                    f"No puede recibir más de lo enviado para '{prod_name}'.\n"
                    f"Enviado: {qty_sent:.3f} | Intentando recibir: {qty_recv:.3f}",
                ); return
            received_items.append(
                ReceiveTransferItem(product_id=product_id, quantity_received=qty_recv)
            )

        cmd = ReceiveTransferCommand(
            operation_id=new_uuid(),
            branch_id=str(self._transfer.get("branch_dest_id", "")),
            user_name=recv_by,
            transfer_id=str(self._transfer["id"]),
            received_by=recv_by,
            received_items=tuple(received_items),
            observations=self._e_obs.toPlainText().strip(),
        )
        try:
            result = self._receive_uc.execute(cmd)
            if result.success:
                diff = float((result.data or {}).get("total_difference", 0))
                detail = f"Diferencia registrada: {diff:.3f} kg" if diff > 0.001 else "Sin diferencias."
                Toast.success(self.parent() or self, "Recepción confirmada", detail)
                self.accept()
            else:
                QMessageBox.warning(self, "Error", result.message)
        except TransferAlreadyReceivedError:
            QMessageBox.warning(self, "Error", "Esta transferencia ya fue recibida.")
        except TransferOverReceptionError as exc:
            QMessageBox.warning(self, "Error", str(exc))
        except TransferError as exc:
            QMessageBox.warning(self, "Error", str(exc))
        except Exception as exc:
            logger.exception("confirmar_recepcion")
            QMessageBox.critical(self, "Error Inesperado", str(exc))


# ── Dialogo Detalle ───────────────────────────────────────────────────────────

class DialogoDetalleTransfer(QDialog):
    def __init__(self, transfer: Dict, items: List[Dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Detalle Transferencia {str(transfer.get('id', ''))[:8]}…")
        self.setMinimumWidth(600)
        lay = QVBoxLayout(self)

        info = QGroupBox("Datos del Traspaso"); il = QFormLayout(info)
        for label, key in [
            ("ID", "id"), ("Estado", "status"),
            ("Origen", "origin_name"), ("Destino", "dest_name"),
            ("Tipo Origen", "origin_type"), ("Tipo Destino", "destination_type"),
            ("Enviado por", "delivered_by"), ("Recibido por", "received_by"),
            ("Fecha Envío", "created_at"), ("Fecha Recepción", "received_at"),
            ("Diferencia Total", "difference_kg"),
        ]:
            val = str(transfer.get(key, "—") or "—")
            if key == "difference_kg":
                val = f"{float(transfer.get(key, 0)):.3f} kg"
            elif len(val) > 16 and "at" in key:
                val = val[:16]
            il.addRow(f"{label}:", QLabel(val))
        lay.addWidget(info)

        grp = QGroupBox("Ítems"); gl = QVBoxLayout(grp)
        tbl = QTableWidget(); tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["Producto", "Enviado", "Recibido", "Diferencia"])
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setRowCount(len(items))
        for ri, item in enumerate(items):
            sent = float(item.get("quantity_sent", item.get("quantity", 0)))
            recv = float(item.get("quantity_received", 0) or 0)
            diff = recv - sent
            for ci, v in enumerate([
                item.get("product_nombre", item.get("nombre", "?")),
                f"{sent:.3f}", f"{recv:.3f}", f"{diff:.3f}",
            ]):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci > 0:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if ci == 3 and abs(diff) > 0.001:
                        it.setForeground(QColor(_C5))
                tbl.setItem(ri, ci, it)
        gl.addWidget(tbl); lay.addWidget(grp)

        btn_close = QPushButton("Cerrar")
        btn_close.setObjectName("secondaryBtn"); btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close)
