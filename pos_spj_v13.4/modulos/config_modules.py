# modulos/config_modules.py — SPJ POS v13
"""
Gestión de Feature Flags — habilitar/deshabilitar módulos por sucursal.
Al desactivar un módulo desaparece del menú lateral inmediatamente.
"""
from __future__ import annotations
from backend.application.queries.module_settings_query_service import ModuleSettingsQueryService
from core.services.feature_flag_service import FeatureFlagService
from modulos.spj_styles import spj_btn, apply_btn_styles
from repositories.feature_flag_repository import FeatureFlagRepository
import logging
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QMessageBox, QCheckBox
)

from core.services.configuration_settings_service import CompanyProfileService
from repositories.config_repository import ConfigRepository

logger = logging.getLogger("spj.config_modules")

MODULOS_SISTEMA = [
    ("POS",              "🛒 Punto de Venta",       True),
    ("CAJA",             "💰 Caja / Cortes Z",       True),
    ("INVENTARIO",       "📦 Inventario",            True),
    ("PRODUCTOS",        "🏷️ Productos",            True),
    ("CLIENTES",         "👥 Clientes",              True),
    ("DELIVERY",         "🛵 Delivery",              True),
    ("COMPRAS",          "🛒 Compras a Prov.",       True),
    ("COTIZACIONES",     "📋 Cotizaciones",          True),
    ("MERMA",            "🗑️ Merma",                True),
    # ("PROVEEDORES",      "🏭 Proveedores",           True),  # ELIMINADO: Integrado en FINANZAS_UNIFICADAS
    ("ETIQUETAS",        "🏷️ Etiquetas",            True),
    ("FINANZAS_UNIFICADAS", "💰 Finanzas",          True),
    ("CUENTAS_XC_XP",   "⚖️ CxC y CxP",            True),
    ("RRHH",             "👔 Recursos Humanos",      True),
    ("ACTIVOS",          "🏢 Activos Fijos",         True),
    ("TARJETAS_FIDELIDAD","💳 Tarjetas Fidelidad",  True),
    ("LOYALTY_CARD",     "🎨 Diseñador Tarjetas",    True),
    ("INTELIGENCIA_BI",  "📊 Inteligencia BI",       True),
    ("PREDICCIONES",     "🔮 Predicciones",          True),
    ("PRODUCCION",       "🏭 Producción",            True),
    ("DELIVERY_AUTO",    "🤖 Auto-asign Delivery",   True),
]


class ModuloConfigModulos(QWidget):

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.db          = container.db
        self.sucursal_id = getattr(container, 'sucursal_id', 1)
        self.module_settings_query_service = ModuleSettingsQueryService(self.db)
        self.feature_flag_service = getattr(container, 'feature_flag_service', None)
        if self.feature_flag_service is None:
            self.feature_flag_service = FeatureFlagService(FeatureFlagRepository(self.db))
        self._build_ui()
        self._cargar()

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        pass

    def set_sucursal(self, sucursal_id, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id
        self._cargar()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)

        hdr = QHBoxLayout()
        titulo = QLabel("🔌 Módulos del sistema")
        titulo.setStyleSheet("font-size:17px;font-weight:bold;")

        self.cmb_sucursal = QComboBox()
        self._cargar_sucursales()
        self.cmb_sucursal.currentIndexChanged.connect(
            lambda _: self._cargar())

        hdr.addWidget(titulo); hdr.addStretch()
        hdr.addWidget(QLabel("Sucursal:")); hdr.addWidget(self.cmb_sucursal)
        lay.addLayout(hdr)

        info = QLabel(
            "Activa o desactiva módulos para cada sucursal. "
            "Los módulos desactivados desaparecen del menú lateral de esa sucursal."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#666;font-size:11px;padding:4px;")
        lay.addWidget(info)

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(4)
        self.tbl.setHorizontalHeaderLabels(["Módulo", "Descripción", "Estado", "Acción"])
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0, 2, 3): hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setVisible(False)
        lay.addWidget(self.tbl)

        btn_row = QHBoxLayout()
        btn_all_on  = QPushButton("✅ Activar todos")
        btn_all_on.clicked.connect(lambda: self._toggle_todos(True))
        btn_all_off = QPushButton("❌ Desactivar todos")
        btn_all_off.clicked.connect(lambda: self._toggle_todos(False))
        btn_row.addWidget(btn_all_on); btn_row.addWidget(btn_all_off); btn_row.addStretch()
        lay.addLayout(btn_row)

    def _cargar_sucursales(self):
        self.cmb_sucursal.blockSignals(True)
        self.cmb_sucursal.clear()
        try:
            rows = self.module_settings_query_service.list_active_branch_options()
            self.cmb_sucursal.blockSignals(True)
            self.cmb_sucursal.clear()
            for r in rows:
                self.cmb_sucursal.addItem(r[1], r[0])
            self.cmb_sucursal.blockSignals(False)
        except Exception:
            self.cmb_sucursal.addItem("Principal", 1)

    def _cargar(self):
        suc_id = self.cmb_sucursal.currentData() or self.sucursal_id
        flags = self.module_settings_query_service.get_branch_feature_flags(suc_id)

        self.tbl.setRowCount(len(MODULOS_SISTEMA))
        for ri, (codigo, nombre, default) in enumerate(MODULOS_SISTEMA):
            activo = flags.get(codigo, default)
            estado_txt = "✅ Activo" if activo else "❌ Inactivo"

            it_cod = QTableWidgetItem(codigo)
            it_cod.setData(Qt.UserRole, codigo)
            it_cod.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            it_nom = QTableWidgetItem(nombre)
            it_nom.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            it_est = QTableWidgetItem(estado_txt)
            it_est.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            if not activo:
                it_est.setForeground(Qt.red)

            self.tbl.setItem(ri, 0, it_cod)
            self.tbl.setItem(ri, 1, it_nom)
            self.tbl.setItem(ri, 2, it_est)

            btn = QPushButton("Desactivar" if activo else "Activar")
            btn.setStyleSheet(
                "background:#e74c3c;color:white;padding:3px 8px;border-radius:3px;"
                if activo else
                "background:#27ae60;color:white;padding:3px 8px;border-radius:3px;"
            )
            btn.clicked.connect(
                lambda _, c=codigo, a=activo: self._toggle(c, not a))
            self.tbl.setCellWidget(ri, 3, btn)

    def _toggle(self, codigo: str, activo: bool):
        suc_id = self.cmb_sucursal.currentData() or self.sucursal_id
        if self.feature_flag_service is None or suc_id is None:
            logger.warning("_toggle %s: feature_flag_service/sucursal no disponible", codigo)
            return
        try:
            self.feature_flag_service.set_flag(codigo, suc_id, activo)
        except Exception as e:
            logger.warning("_toggle %s: %s", codigo, e)

        # Actualizar menú lateral si está disponible
        try:
            main_win = self.window()
            if hasattr(main_win, 'menu') and hasattr(main_win.menu, 'set_permisos'):
                # Re-propagar permisos
                if hasattr(main_win, '_propagar_usuario'):
                    main_win._propagar_usuario(main_win.usuario_actual or {})
        except Exception:
            pass

        self._cargar()

    def _toggle_todos(self, activo: bool):
        resp = QMessageBox.question(
            self, "Confirmar",
            f"¿{'Activar' if activo else 'Desactivar'} TODOS los módulos?",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes: return
        for codigo, _, _ in MODULOS_SISTEMA:
            self._toggle(codigo, activo)
