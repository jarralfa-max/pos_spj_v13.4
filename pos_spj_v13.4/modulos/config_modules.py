# modulos/config_modules.py — SPJ POS v13
"""
Gestión de Feature Flags — habilitar/deshabilitar módulos por sucursal.
Al desactivar un módulo desaparece del menú lateral inmediatamente.
"""
from __future__ import annotations
from modulos.spj_styles import spj_btn, apply_btn_styles
import logging
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QMessageBox, QCheckBox
)

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
    ("PROVEEDORES",      "🏭 Proveedores",           True),
    ("ETIQUETAS",        "🏷️ Etiquetas",            True),
    ("CUENTAS_XC_XP",   "⚖️ CxC y CxP",            True),
    ("TESORERIA",        "🏦 Tesorería",             True),
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
        self._build_ui()
        self._cargar()

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        pass

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
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
        btn_all_on  = QPushButton("✅ Activar todos"); btn_all_on.setObjectName("successBtn")
        btn_all_on.clicked.connect(lambda: self._toggle_todos(True))
        btn_all_off = QPushButton("❌ Desactivar todos"); btn_all_off.setObjectName("dangerBtn")
        btn_all_off.clicked.connect(lambda: self._toggle_todos(False))
        btn_row.addWidget(btn_all_on); btn_row.addWidget(btn_all_off); btn_row.addStretch()
        lay.addLayout(btn_row)

    def _cargar_sucursales(self):
        try:
            rows = self.db.execute(
                "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre"
            ).fetchall()
            self.cmb_sucursal.blockSignals(True)
            self.cmb_sucursal.clear()
            for r in rows:
                self.cmb_sucursal.addItem(r[1], r[0])
            self.cmb_sucursal.blockSignals(False)
        except Exception:
            self.cmb_sucursal.addItem("Principal", 1)

    def _cargar(self):
        suc_id = self.cmb_sucursal.currentData() or self.sucursal_id
        # Load current flags from DB
        flags = {}
        try:
            rows = self.db.execute(
                "SELECT clave, activo FROM feature_flags"
            ).fetchall()
            flags = {r[0]: bool(r[1]) for r in rows}
        except Exception:
            pass

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
            btn.setObjectName("dangerBtn" if activo else "successBtn")
            btn.clicked.connect(
                lambda _, c=codigo, a=activo: self._toggle(c, not a))
            self.tbl.setCellWidget(ri, 3, btn)

    def _toggle(self, codigo: str, activo: bool):
        suc_id = self.cmb_sucursal.currentData() or self.sucursal_id
        try:
            ffs = getattr(self.container, 'feature_flag_service', None)
            if ffs and hasattr(ffs, 'repo') and hasattr(ffs.repo, 'set_flag'):
                ffs.repo.set_flag(codigo, suc_id, activo)
                ffs._cache.pop(suc_id, None)  # invalidate cache
            else:
                # Fallback: direct DB
                self.db.execute("""
                    INSERT INTO feature_flags(clave, activo, descripcion)
                    VALUES(?,?,?)
                    ON CONFLICT(clave) DO UPDATE SET activo=excluded.activo
                """, (codigo, int(activo), codigo))
                try: self.db.commit()
                except Exception: pass
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
