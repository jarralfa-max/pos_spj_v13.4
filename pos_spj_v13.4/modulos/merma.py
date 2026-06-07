# modulos/merma.py — SPJ POS v13.4
"""Módulo de registro de merma usando la ruta canónica backend."""
from __future__ import annotations

import logging
import uuid

from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QGroupBox, QDateEdit, QMessageBox,
    QInputDialog, QTabWidget,
)

from backend.application.commands.waste_commands import RegisterWasteCommand
from backend.application.queries.waste_query_service import WasteQueryService
from backend.application.services.waste_application_service import WasteApplicationService, WasteFinanceHandler
from backend.application.use_cases.register_waste_use_case import RegisterWasteUseCase
from backend.infrastructure.db.repositories.waste_repository import WasteRepository
from backend.shared.events.event_bus import InMemoryEventBus
from frontend.desktop.components.search_selector import SearchOption, SearchSelector
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_primary_button, create_secondary_button, create_input, create_combo,
    FilterBar, LoadingIndicator, EmptyStateWidget, Toast,
)

logger = logging.getLogger("spj.modulo.merma")

UMBRAL_VALOR_ALTO = 500.0


def _safe_float(value, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning("[MERMA] valor numérico inválido value=%r", value)
        return default


class ModuloMerma(QWidget):
    """Registro, visualización y auditoría de merma diaria."""

    MOTIVOS = [
        "Caducidad / vencimiento",
        "Evaporación / deshidratación",
        "Recorte en proceso",
        "Daño en manipulación",
        "Contaminación",
        "Error de proceso",
        "Robo interno",
        "Devolución no reingresable",
        "Otro",
    ]

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self.sucursal_id = getattr(container, "sucursal_id", 1)
        self.usuario = ""
        self._selected_product: dict | None = None
        self._product_search_cache: dict[str, dict] = {}
        self._build_backend_services(container)
        self._build_ui()
        logger.info("[MERMA] módulo inicializado sucursal_id=%s", self.sucursal_id)
        self._cargar_historial()

    def _build_backend_services(self, container) -> None:
        repository = WasteRepository(container.db)
        self._waste_repository = repository
        event_bus = getattr(container, "waste_event_bus", None) or InMemoryEventBus()
        finance_service = getattr(container, "finance_service", None) or getattr(container, "treasury_service", None)
        finance_handler = WasteFinanceHandler(finance_service)
        self._waste_query_service = WasteQueryService(repository)
        self._register_waste_use_case = RegisterWasteUseCase(
            app_service=WasteApplicationService(
                repository=repository,
                event_bus=event_bus,
                finance_handler=finance_handler,
            )
        )

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        self.usuario = usuario

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id
        self._cargar_historial()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        titulo = QLabel("🗑️ Control de Merma")
        titulo.setObjectName("heading")
        hdr.addWidget(titulo)
        hdr.addStretch()
        self.lbl_resumen = QLabel()
        self.lbl_resumen.setObjectName("caption")
        self.lbl_resumen.setStyleSheet(f"color: {Colors.DANGER_BASE}; font-weight: bold;")
        hdr.addWidget(self.lbl_resumen)
        lay.addLayout(hdr)

        tabs = QTabWidget()
        tabs.setObjectName("tabWidget")
        tab_reg = QWidget()
        self._build_tab_registro(tab_reg)
        tabs.addTab(tab_reg, "📝 Registrar Merma")
        tab_hist = QWidget()
        self._build_tab_historial(tab_hist)
        tabs.addTab(tab_hist, "📋 Historial")
        lay.addWidget(tabs)

    def _build_tab_registro(self, parent):
        lay = QVBoxLayout(parent)
        lay.setSpacing(10)

        grp = QGroupBox("Datos de la merma")
        grp.setObjectName("styledGroup")
        form = QFormLayout(grp)
        form.setSpacing(8)

        self.product_selector = SearchSelector(
            self,
            provider=self._buscar_productos,
            placeholder="🔍 Buscar producto por nombre...",
        )
        self.product_selector.selected.connect(self._on_producto_selected)
        form.addRow("Producto:", self.product_selector)

        self.lbl_producto_info = QLabel("")
        self.lbl_producto_info.setObjectName("caption")
        form.addRow("", self.lbl_producto_info)

        self.spin_cantidad = QDoubleSpinBox()
        self.spin_cantidad.setRange(0.00, 99999.00)
        self.spin_cantidad.setDecimals(2)
        self.spin_cantidad.setValue(0.00)
        self.spin_cantidad.setStyleSheet(f"padding: {Spacing.XS}; font-size: {Typography.SIZE_SM};")
        self.spin_cantidad.valueChanged.connect(self._actualizar_valor_perdida)
        form.addRow("Cantidad:", self.spin_cantidad)

        self.lbl_valor_perdida = QLabel("$0.00")
        self.lbl_valor_perdida.setObjectName("heading")
        self.lbl_valor_perdida.setStyleSheet(f"color: {Colors.DANGER_BASE};")
        form.addRow("Valor pérdida:", self.lbl_valor_perdida)

        self.cmb_motivo = create_combo(self, self.MOTIVOS)
        form.addRow("Motivo:", self.cmb_motivo)

        self.txt_notas = create_input(self, "Observaciones (opcional)")
        form.addRow("Notas:", self.txt_notas)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setObjectName("inputField")
        form.addRow("Fecha:", self.date_edit)

        lay.addWidget(grp)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_guardar = create_primary_button(self, "🗑️ Registrar Merma", "Confirmar el registro de la merma seleccionada")
        btn_guardar.clicked.connect(self._registrar)
        btn_row.addWidget(btn_guardar)
        lay.addLayout(btn_row)
        lay.addStretch()

    def _build_tab_historial(self, parent):
        lay = QVBoxLayout(parent)
        filt = QHBoxLayout()
        lbl_periodo = QLabel("Período:")
        lbl_periodo.setObjectName("caption")
        filt.addWidget(lbl_periodo)
        self.cmb_periodo = create_combo(self, ["Hoy", "Última semana", "Último mes", "Todo"])
        self.cmb_periodo.currentIndexChanged.connect(self._cargar_historial)
        filt.addWidget(self.cmb_periodo)
        filt.addStretch()
        btn_refresh = create_secondary_button(self, "🔄 Actualizar", "Recargar el historial de mermas")
        btn_refresh.clicked.connect(self._cargar_historial)
        filt.addWidget(btn_refresh)
        lay.addLayout(filt)
        self._hist_filter = FilterBar(
            self,
            placeholder="Buscar producto, motivo o usuario…",
            combo_filters={"periodo": ["Hoy", "Última semana", "Último mes", "Todo"]},
        )
        self._hist_filter.filters_changed.connect(lambda _v: self._cargar_historial())
        lay.addWidget(self._hist_filter)
        self._hist_loading = LoadingIndicator("Cargando historial de merma…", self)
        self._hist_loading.hide()
        lay.addWidget(self._hist_loading)

        self.tbl = QTableWidget()
        self.tbl.setObjectName("tableView")
        self.tbl.setColumnCount(9)
        self.tbl.setHorizontalHeaderLabels([
            "Fecha", "Producto", "Cantidad", "Unidad",
            "Costo/u", "Valor Pérdida", "Motivo", "Usuario", "Notas",
        ])
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setVisible(False)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(6, QHeaderView.Stretch)
        lay.addWidget(self.tbl, 1)
        self._hist_empty = EmptyStateWidget(
            "Sin registros de merma",
            "No hay registros para el período o filtros seleccionados.",
            "📭",
            self,
        )
        self._hist_empty.hide()
        lay.addWidget(self._hist_empty)
        self.lbl_total_hist = QLabel()
        self.lbl_total_hist.setObjectName("caption")
        self.lbl_total_hist.setStyleSheet(f"font-weight: bold; color: {Colors.DANGER_BASE};")
        lay.addWidget(self.lbl_total_hist)

    def _buscar_productos(self, query: str):
        logger.info("[MERMA] búsqueda ejecutada query=%r", query)
        try:
            results = self._waste_query_service.search_products(query, {"branch_id": str(self.sucursal_id)})
        except Exception:
            logger.exception("[MERMA] error al buscar productos query=%r", query)
            self._product_search_cache = {}
            return []

        self._product_search_cache = {str(result.id): dict(result.metadata or {}) for result in results}
        options = [
            SearchOption(id=result.id, label=result.label, subtitle=result.subtitle)
            for result in results
        ]
        logger.info("[MERMA] productos encontrados count=%d query=%r", len(results), query)
        logger.info("[MERMA] resultados renderizados count=%d", len(options))
        return options

    def _on_producto_selected(self, option: SearchOption):
        try:
            self._aplicar_producto_seleccionado(option)
        except Exception:
            logger.exception("[MERMA] error seleccionando producto")
            QMessageBox.critical(self, "Error", "No se pudo seleccionar el producto. Revisa el log.")

    def _aplicar_producto_seleccionado(self, option: SearchOption):
        if option is None:
            logger.warning("[MERMA] selección recibida sin opción")
            return

        product_id = str(option.id) if option.id is not None else ""
        logger.info("[MERMA] click en fila product_id=%s label=%s", product_id, option.label)
        logger.info("[MERMA] producto_id recuperado product_id=%s", product_id)
        logger.info(
            "[MERMA] producto seleccionado desde SearchSelector product_id=%s label=%s",
            product_id, option.label,
        )
        if not product_id:
            logger.warning("[MERMA] selección sin producto_id option=%r", option)
            return

        metadata = self._product_search_cache.get(product_id)
        if metadata is None:
            logger.warning("[MERMA] producto_id no encontrado en caché; consultando por id product_id=%s", product_id)
            metadata = self._waste_repository.get_product_for_waste(product_id, branch_id=str(self.sucursal_id))

        if metadata is None:
            self._selected_product = None
            self.lbl_producto_info.setText("")
            self._actualizar_valor_perdida()
            logger.warning("[MERMA] producto no encontrado product_id=%s", product_id)
            return

        metadata = dict(metadata)
        metadata["id"] = metadata.get("id", product_id)
        metadata["name"] = str(metadata.get("name") or option.label or f"Producto #{product_id}")
        metadata["unit"] = str(metadata.get("unit") or "kg")
        metadata["stock"] = _safe_float(metadata.get("stock"))
        metadata["unit_cost"] = _safe_float(metadata.get("unit_cost"))
        self._selected_product = metadata
        logger.info(
            "[MERMA] metadata seleccionada id=%s stock=%.2f unit=%s cost=%.2f",
            metadata.get("id"), metadata["stock"], metadata["unit"], metadata["unit_cost"],
        )

        self.product_selector.set_selected_label(option.label)

        unidad = metadata["unit"]
        stock = metadata["stock"]
        costo = metadata["unit_cost"]
        self.spin_cantidad.setSuffix(f" {unidad}")
        self.lbl_producto_info.setText(f"Stock actual: {stock:.2f} {unidad}  |  Costo: ${costo:.2f}/{unidad}")
        self._actualizar_valor_perdida()
        logger.info(
            "[MERMA] UI actualizada product_id=%s unidad=%s stock=%.2f costo=%.2f",
            metadata.get("id"), unidad, stock, costo,
        )

    def _actualizar_valor_perdida(self):
        if self._selected_product:
            costo = _safe_float(self._selected_product.get("unit_cost"))
            cantidad = self.spin_cantidad.value()
            valor = round(cantidad * costo, 2)
            self.lbl_valor_perdida.setText(f"${valor:.2f}")
            if valor >= UMBRAL_VALOR_ALTO:
                self.lbl_valor_perdida.setStyleSheet(
                    f"font-size: {Typography.SIZE_LG}; font-weight: bold; color: {Colors.TEXT_INVERTED}; "
                    f"background-color: {Colors.DANGER_BASE}; padding: {Spacing.XS} {Spacing.SM}; border-radius: {Borders.RADIUS_MD};")
            else:
                self.lbl_valor_perdida.setStyleSheet(
                    f"font-size: {Typography.SIZE_LG}; font-weight: bold; color: {Colors.DANGER_BASE}; "
                    f"padding: {Spacing.XS} {Spacing.SM}; background-color: {Colors.DANGER.BG_SOFT}; border-radius: {Borders.RADIUS_MD};")
        else:
            self.lbl_valor_perdida.setText("$0.00")

    def _registrar(self) -> None:
        try:
            self._registrar_seguro()
        except Exception:
            logger.exception("[MERMA] error registrando merma")
            QMessageBox.critical(self, "Error", "No se pudo registrar la merma. Revisa el log.")

    def _registrar_seguro(self) -> None:
        from core.permissions import verificar_permiso
        try:
            if not verificar_permiso(self.container, "MERMA.crear", self):
                logger.warning("[MERMA] Permiso denegado para registrar merma: MERMA.crear")
                return
        except Exception:
            logger.exception("[MERMA] No se pudo validar el permiso MERMA.crear")
            QMessageBox.critical(self, "Error", "No se pudo validar el permiso para registrar merma.")
            return

        if not self._selected_product:
            QMessageBox.warning(self, "Aviso", "Selecciona un producto.")
            return
        cantidad = self.spin_cantidad.value()
        if cantidad <= 0:
            QMessageBox.warning(self, "Aviso", "La cantidad debe ser > 0.")
            return

        product = self._selected_product
        product_id = product.get("id")
        if product_id in (None, ""):
            logger.warning("[MERMA] registro de merma sin product_id product=%r", product)
            QMessageBox.warning(self, "Aviso", "El producto seleccionado no tiene un ID válido.")
            return
        nombre = str(product.get("name", ""))
        unidad = str(product.get("unit", "kg"))
        stock_actual = _safe_float(product.get("stock"))
        costo_unitario = _safe_float(product.get("unit_cost"))
        motivo = self.cmb_motivo.currentText()
        notas = self.txt_notas.text().strip()
        fecha = self.date_edit.date().toString("yyyy-MM-dd")
        valor_perdida = round(cantidad * costo_unitario, 2)
        logger.info(
            "[MERMA] registro de merma iniciado product_id=%s quantity=%.2f",
            product_id, cantidad,
        )
        logger.info(
            "[MERMA] validación stock actual=%.2f cantidad=%.2f",
            stock_actual, cantidad,
        )
        logger.info("[MERMA] registro de merma product_id usado product_id=%s", product_id)

        if cantidad > stock_actual:
            resp = QMessageBox.warning(
                self, "⚠️ Stock insuficiente",
                f"La merma ({cantidad:.2f} {unidad}) es mayor al stock actual "
                f"({stock_actual:.2f} {unidad}).\n\n"
                "La cantidad supera el stock. La existencia se ajustará a cero y "
                "la diferencia quedará documentada para auditoría.\n"
                "¿Registrar de todas formas?",
                QMessageBox.Yes | QMessageBox.No)
            if resp != QMessageBox.Yes:
                return

        if valor_perdida >= UMBRAL_VALOR_ALTO:
            resp = QMessageBox.warning(
                self, "⚠️ Merma de alto valor",
                f"Esta merma tiene un valor de ${valor_perdida:.2f}\n"
                f"({cantidad:.2f} {unidad} × ${costo_unitario:.2f}/{unidad})\n\n"
                f"Producto: {nombre}\n"
                f"Motivo: {motivo}\n\n"
                "¿Confirmar el registro?",
                QMessageBox.Yes | QMessageBox.No)
            if resp != QMessageBox.Yes:
                return
            if not self._validar_pin_alto_valor(nombre, valor_perdida):
                return

        operation_id = str(uuid.uuid4())
        result = self._register_waste_use_case.execute(RegisterWasteCommand(
            operation_id=operation_id,
            branch_id=str(self.sucursal_id),
            user_name=self.usuario or "usuario",
            product_id=product_id,
            quantity=cantidad,
            reason=motivo,
            notes=notas,
            date=fecha,
            unit=unidad,
            manager_pin_authorized=valor_perdida >= UMBRAL_VALOR_ALTO,
        ))
        logger.info(
            "[MERMA] use_case result success=%s entity_id=%s message=%s",
            result.success, result.entity_id, result.message,
        )
        if not result.success:
            QMessageBox.critical(self, "Error", result.message or "No se pudo registrar la merma.")
            return

        self._registrar_auditoria(result.entity_id or operation_id, nombre, cantidad, unidad, costo_unitario, valor_perdida, motivo)
        Toast.success(
            self, "✅ Merma registrada",
            f"{cantidad:.2f} {unidad} '{nombre}' · ${valor_perdida:.2f} · {motivo}",
        )
        self._limpiar_formulario()
        self._cargar_historial()

    def _validar_pin_alto_valor(self, nombre: str, valor_perdida: float) -> bool:
        pin, ok_pin = QInputDialog.getText(
            self,
            "Autorización requerida",
            "Ingresa PIN de gerente/admin para autorizar la merma:",
            QLineEdit.Password,
        )
        if not ok_pin or not pin:
            QMessageBox.warning(self, "Autorización", "Operación cancelada: PIN requerido.")
            return False
        from core.permissions import verificar_permiso
        if not verificar_permiso(self.container, "MERMA.autorizar", self):
            return False
        from core.services.discount_guard import DiscountGuard
        try:
            guard = DiscountGuard(self.container.db)
            if guard.solicitar_pin_gerente(self.container.db, pin):
                return True
            QMessageBox.critical(self, "Autorización rechazada", "PIN inválido o sin permisos de gerente/admin.")
            self._registrar_denegacion_pin(nombre, valor_perdida)
            return False
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo validar PIN: {exc}")
            return False

    def _registrar_denegacion_pin(self, nombre: str, valor_perdida: float) -> None:
        from core.services.auto_audit import audit_write
        try:
            audit_write(
                self.container, modulo="MERMA", accion="MERMA_DENEGADA_PIN",
                entidad="mermas", entidad_id="", usuario=self.usuario,
                sucursal_id=self.sucursal_id,
                detalles=f"Intento de merma alta sin PIN válido. Producto={nombre} Valor={valor_perdida:.2f}",
            )
        except Exception:
            logger.exception("[MERMA] No se pudo registrar auditoría de PIN denegado")

    def _registrar_auditoria(self, waste_id: str, nombre: str, cantidad: float, unidad: str,
                             costo_unitario: float, valor_perdida: float, motivo: str) -> None:
        from core.services.auto_audit import audit_write
        try:
            audit_write(
                self.container, modulo="MERMA", accion="REGISTRAR_MERMA",
                entidad="mermas", entidad_id=waste_id, usuario=self.usuario,
                sucursal_id=self.sucursal_id,
                detalles=(f"Producto: {nombre} | Cant: {cantidad:.2f} {unidad} | "
                          f"Costo: ${costo_unitario:.2f}/u | "
                          f"Pérdida: ${valor_perdida:.2f} | Motivo: {motivo}"),
            )
        except Exception:
            logger.exception("[MERMA] No se pudo registrar auditoría de merma")

    def _limpiar_formulario(self) -> None:
        self.spin_cantidad.setValue(0.00)
        self.txt_notas.clear()
        self._selected_product = None
        self.lbl_producto_info.setText("")
        self.lbl_valor_perdida.setText("$0.00")
        self.product_selector.clear()

    def _cargar_historial(self):
        if hasattr(self, "_hist_loading"):
            self._hist_loading.show()
        try:
            periodo = self.cmb_periodo.currentText() if hasattr(self, "cmb_periodo") else "Hoy"
            if hasattr(self, "_hist_filter"):
                periodo = self._hist_filter.values().get("periodo") or periodo
            search = ""
            if hasattr(self, "_hist_filter"):
                search = (self._hist_filter.values().get("search") or "").strip()
            rows = self._waste_query_service.list_for_table({
                "branch_id": str(self.sucursal_id),
                "period": periodo,
                "search": search,
            })
            self.tbl.setRowCount(len(rows))
            total_valor = 0.0
            total_cantidad = 0.0
            for ri, row in enumerate(rows):
                values = row.values
                cant = _safe_float(values.get("quantity"))
                valor = _safe_float(values.get("loss_value"))
                vals = [
                    values.get("date", ""),
                    values.get("product_name", ""),
                    f"{cant:.2f}",
                    values.get("unit", "kg"),
                    f"${_safe_float(values.get('unit_cost')):.2f}",
                    f"${valor:.2f}",
                    values.get("reason", ""),
                    values.get("user_name", ""),
                    values.get("notes", ""),
                ]
                for ci, value in enumerate(vals):
                    item = QTableWidgetItem(str(value))
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if ci in (2, 4, 5):
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if ci == 5 and valor >= UMBRAL_VALOR_ALTO:
                        item.setForeground(QColor(Colors.DANGER_HOVER))
                        item.setFont(QFont("Arial", -1, QFont.Bold))
                    self.tbl.setItem(ri, ci, item)
                total_valor += valor
                total_cantidad += cant

            n_registros = len(rows)
            if hasattr(self, "lbl_total_hist"):
                self.lbl_total_hist.setText(
                    f"Total período: {n_registros} registros  |  "
                    f"Cantidad: {total_cantidad:.2f}  |  "
                    f"Valor pérdida: ${total_valor:.2f}")
            if hasattr(self, "_hist_empty"):
                self._hist_empty.setVisible(n_registros == 0)
            summary = self._waste_query_service.get_daily_summary({"branch_id": str(self.sucursal_id)}).value
            self.lbl_resumen.setText(
                f"Hoy: {int(summary.get('records', 0))} mermas  —  "
                f"Pérdida: ${_safe_float(summary.get('loss_value')):.2f}")
            logger.info("[MERMA] historial cargado count=%d", n_registros)
        except Exception:
            logger.exception("[MERMA] _cargar_historial falló")
            self.lbl_resumen.setText("Hoy: —")
        finally:
            if hasattr(self, "_hist_loading"):
                self._hist_loading.hide()
