# modulos/inventario_local.py — SPJ POS v13.2
from __future__ import annotations
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography
from modulos.ui_components import (
    create_primary_button, create_success_button, create_secondary_button,
    create_input_field, apply_tooltip, FilterBar, LoadingIndicator, EmptyStateWidget,
    PageHeader, Toast,
)
import logging
from modulos.spj_refresh_mixin import RefreshMixin
from core.events.event_bus import VENTA_COMPLETADA, PRODUCTO_ACTUALIZADO, PRODUCTO_CREADO, AJUSTE_INVENTARIO, COMPRA_REGISTRADA
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QInputDialog, QLineEdit, QFileDialog, QComboBox,
)
from PyQt5.QtCore import Qt

logger = logging.getLogger("spj.inventario")


class ModuloInventarioLocal(QWidget, RefreshMixin):

    def __init__(self, container, parent=None):
        super().__init__(parent)
        try: self._init_refresh(container, ["VENTA_COMPLETADA", "PRODUCTO_ACTUALIZADO", "PRODUCTO_CREADO", "AJUSTE_INVENTARIO", "COMPRA_REGISTRADA"])
        except Exception: pass
        self.container     = container
        self.sucursal_id   = 1
        self.usuario_actual = ""
        self.init_ui()

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str = ""):
        self.sucursal_id = sucursal_id
        self.lbl_titulo.setText(f"📦 Inventario — {nombre_sucursal}")
        self.cargar_datos()

    def set_usuario_actual(self, usuario: str, rol: str = ""):
        self.usuario_actual = usuario

    def init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._page_header = PageHeader(
            self,
            title="📦 Inventario Local",
            subtitle="Stock por sucursal, ajustes y exportaciones",
        )
        lay.addWidget(self._page_header)

        body = QWidget(self)
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        body_lay.setSpacing(Spacing.MD)
        lay.addWidget(body, 1)
        lay = body_lay  # subsequent additions land in the body

        # Search + actions
        ctrl = QHBoxLayout()
        ctrl.setSpacing(Spacing.SM)
        self._filter_bar = FilterBar(self, placeholder="Buscar producto o categoría…")
        self._filter_bar.filters_changed.connect(lambda _v: self.cargar_datos())
        ctrl.addWidget(self._filter_bar, 1)
        
        btn_ref = QPushButton("🔄")
        btn_ref.setFixedWidth(36)
        btn_ref.setObjectName("secondaryBtn")
        apply_tooltip(btn_ref, "Refrescar inventario")
        btn_ref.clicked.connect(self.cargar_datos)
        
        btn_ajuste = create_secondary_button(self, "⚖️ Ajuste", "Registrar ajuste de inventario")
        btn_ajuste.clicked.connect(self.abrir_dialogo_ajuste)
        
        btn_exp_csv = create_success_button(self, "📊 Exportar CSV", "Exportar inventario a CSV")
        btn_exp_csv.clicked.connect(lambda: self._exportar("csv"))
        
        btn_exp_xls = create_primary_button(self, "📑 Exportar Excel", "Exportar inventario a Excel")
        btn_exp_xls.clicked.connect(lambda: self._exportar("xlsx"))
        
        ctrl.addWidget(btn_ref)
        ctrl.addWidget(btn_ajuste)
        ctrl.addWidget(btn_exp_csv)
        ctrl.addWidget(btn_exp_xls)
        lay.addLayout(ctrl)
        self._loading = LoadingIndicator("Cargando inventario…", self)
        self._loading.hide()
        lay.addWidget(self._loading)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(["ID", "Producto", "Categoría", "Stock", "Unidad"])
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setObjectName("tableView")
        lay.addWidget(self.tabla)
        self._empty_state = EmptyStateWidget(
            "Sin productos",
            "No se encontraron productos para los filtros seleccionados.",
            "📭",
            self,
        )
        self._empty_state.hide()
        lay.addWidget(self._empty_state)

        self.lbl_total = QLabel("")
        self.lbl_total.setObjectName("caption")
        lay.addWidget(self.lbl_total)

        self.cargar_datos()

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh inventory on any stock change event."""
        try: self.cargar_datos()
        except Exception: pass

    def cargar_datos(self):
        if hasattr(self, "_loading"):
            self._loading.show()
        try:
            buscar = ""
            if hasattr(self, "_filter_bar"):
                buscar = self._filter_bar.values().get("search", "").strip()
            self.tabla.setRowCount(0)
            try:
                db = self.container.db
                q = ("SELECT p.id, p.nombre, COALESCE(p.categoria,''), "
                     "COALESCE(bi.quantity, p.existencia, 0), COALESCE(p.unidad,'pza') "
                     "FROM productos p "
                     "LEFT JOIN branch_inventory bi ON bi.product_id=p.id AND bi.branch_id=? "
                     "WHERE p.activo=1")
                params = [self.sucursal_id]
                if buscar:
                    q += " AND (p.nombre LIKE ? OR p.categoria LIKE ?)"
                    params += [f"%{buscar}%", f"%{buscar}%"]
                q += " ORDER BY p.nombre"
                rows = db.execute(q, params).fetchall()
            except Exception as e:
                logger.warning("cargar inventario: %s", e)
                rows = []
            for i, r in enumerate(rows):
                self.tabla.insertRow(i)
                for j, v in enumerate(r):
                    it = QTableWidgetItem(f"{float(v):.3f}" if j == 3 else str(v) if v else "")
                    if j == 3:
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        if float(v) <= 0:
                            it.setForeground(__import__('PyQt5.QtGui', fromlist=['QColor']).QColor('#e74c3c'))
                    self.tabla.setItem(i, j, it)
            self.lbl_total.setText(f"{len(rows)} productos")
            if hasattr(self, "_empty_state"):
                self._empty_state.setVisible(len(rows) == 0)
        finally:
            if hasattr(self, "_loading"):
                self._loading.hide()

    def abrir_dialogo_ajuste(self):
        # v13.30: Verificar permiso
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "inventario.ajustar", self):
                return
        except Exception: pass
        row = self.tabla.currentRow()
        if row < 0:
            QMessageBox.warning(self,"Aviso","Seleccione un producto."); return
        prod_id   = int(self.tabla.item(row,0).text())
        nombre    = self.tabla.item(row,1).text()
        stock_act = float(self.tabla.item(row,3).text())
        nuevo, ok = QInputDialog.getDouble(
            self,"Ajuste de Inventario",
            f"Producto: {nombre}\nStock sistema: {stock_act:.3f}\nConteo físico real:",
            value=stock_act, min=0, max=999999, decimals=3)
        if not ok or nuevo == stock_act: return
        motivo, ok2 = QInputDialog.getText(self,"Motivo","Razón del ajuste (para auditoría):")
        if not ok2 or not motivo.strip():
            QMessageBox.warning(self,"Aviso","El motivo es obligatorio."); return
        try:
            uc = getattr(self.container, "uc_inventario", None)
            if uc:
                r = uc.registrar_ajuste(prod_id, nuevo, self.sucursal_id,
                                         self.usuario_actual, motivo)
                if not r.ok: raise Exception(r.error)
            else:
                inv = self.container.inventory_service
                inv.execute_manual_adjustment(prod_id, self.sucursal_id,
                                               nuevo, self.usuario_actual, motivo)
            Toast.success(self, "Inventario ajustado", "El ajuste se guardó correctamente.")
            self.cargar_datos()
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _exportar(self, fmt: str):
        """Exporta inventario a CSV o Excel."""
        rows = []
        for i in range(self.tabla.rowCount()):
            rows.append([
                self.tabla.item(i,j).text() if self.tabla.item(i,j) else ""
                for j in range(self.tabla.columnCount())
            ])
        headers = ["ID","Producto","Categoría","Stock","Unidad"]
        if fmt == "csv":
            path, _ = QFileDialog.getSaveFileName(self,"Exportar CSV","inventario.csv","CSV (*.csv)")
            if not path: return
            try:
                import csv
                with open(path,'w',newline='',encoding='utf-8') as f:
                    w = csv.writer(f)
                    w.writerow(headers); w.writerows(rows)
                Toast.success(self, "Exportado", path)
            except Exception as e:
                QMessageBox.critical(self,"Error",str(e))
        else:
            path, _ = QFileDialog.getSaveFileName(self,"Exportar Excel","inventario.xlsx","Excel (*.xlsx)")
            if not path: return
            try:
                import openpyxl
                wb = openpyxl.Workbook(); ws = wb.active
                ws.append(headers)
                for r in rows: ws.append(r)
                wb.save(path)
                Toast.success(self, "Exportado", path)
            except ImportError:
                # Fallback to CSV if openpyxl not installed
                path2 = path.replace('.xlsx','.csv')
                import csv
                with open(path2,'w',newline='',encoding='utf-8') as f:
                    csv.writer(f).writerows([headers]+rows)
                Toast.info(self, "Guardado como CSV", f"openpyxl no instalado — {path2}")
            except Exception as e:
                QMessageBox.critical(self,"Error",str(e))
