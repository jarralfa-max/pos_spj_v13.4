from __future__ import annotations

"""Runtime compatibility bootstrap for the ERP desktop process.

This file is imported automatically by Python when the ERP is executed from the
`pos_spj_v13.4/pos_spj_v13.4` directory. It keeps optional cross-package imports
working without changing business logic.

Fixes covered here:
- Make `<repo_root>/whatsapp_service` importable from the ERP process.
- Make legacy imports used inside whatsapp_service (`from parser...`, `from models...`)
  work when the package is loaded from the ERP.
- Add safe no-crash wrappers to the redesigned Delivery UI when the class is
  imported with calls to `_safe_*` methods that were not defined.
"""

import importlib.abc
import importlib.machinery
import sys
from pathlib import Path


def _add_repo_paths() -> tuple[str, str]:
    current = Path(__file__).resolve()
    for parent in current.parents:
        service_dir = parent / "whatsapp_service"
        erp_dir = parent / "pos_spj_v13.4"
        if service_dir.is_dir() and erp_dir.is_dir():
            repo_root = str(parent)
            service_root = str(service_dir)
            # repo_root makes `import whatsapp_service...` work.
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)
            # service_root keeps legacy microservice imports like `from parser...` working.
            if service_root not in sys.path:
                sys.path.insert(0, service_root)
            return repo_root, service_root
    return "", ""


_add_repo_paths()


def _patch_delivery_module(module) -> None:
    cls = getattr(module, "ModuloDelivery", None)
    if cls is None:
        return

    def _safe_update_filter_tabs(self, pedidos, counts_estado):
        try:
            return self._update_filter_tabs(pedidos, counts_estado)
        except Exception as exc:
            try:
                module.logger.warning("Delivery filter tabs load failed: %s", exc)
            except Exception:
                pass
            return None

    def _safe_update_kpi(self, pedidos):
        try:
            return self._update_kpi(pedidos)
        except Exception as exc:
            try:
                module.logger.warning("Delivery KPI load failed: %s", exc)
            except Exception:
                pass
            return None

    def _safe_refresh_operational_header(self):
        try:
            return self._refresh_operational_header()
        except Exception as exc:
            try:
                module.logger.warning("Delivery header refresh failed: %s", exc)
            except Exception:
                pass
            return None

    def _safe_poll_delivery_notifications(self):
        try:
            return self._poll_delivery_notifications()
        except Exception as exc:
            try:
                module.logger.warning("Delivery notifications load failed: %s", exc)
            except Exception:
                pass
            return None

    def _ensure_driver_history_schema(self):
        try:
            self.conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_driver_cuts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    driver_id INTEGER NOT NULL,
                    driver_nombre TEXT,
                    turno_inicio DATETIME,
                    turno_fin DATETIME DEFAULT (datetime('now')),
                    entregas_total INTEGER DEFAULT 0,
                    efectivo_cobrado REAL DEFAULT 0,
                    tarjeta_cobrado REAL DEFAULT 0,
                    transfer_cobrado REAL DEFAULT 0,
                    total_cobrado REAL DEFAULT 0,
                    efectivo_entregado REAL DEFAULT 0,
                    diferencia REAL DEFAULT 0,
                    usuario_corte TEXT,
                    sucursal_id INTEGER DEFAULT 1,
                    notas TEXT,
                    fecha DATETIME DEFAULT (datetime('now'))
                )
                """
            )
            for col in (
                "driver_nombre TEXT", "turno_inicio DATETIME", "turno_fin DATETIME",
                "entregas_total INTEGER DEFAULT 0", "efectivo_cobrado REAL DEFAULT 0",
                "tarjeta_cobrado REAL DEFAULT 0", "transfer_cobrado REAL DEFAULT 0",
                "total_cobrado REAL DEFAULT 0", "efectivo_entregado REAL DEFAULT 0",
                "diferencia REAL DEFAULT 0", "usuario_corte TEXT", "sucursal_id INTEGER DEFAULT 1",
                "notas TEXT", "fecha DATETIME",
            ):
                try:
                    self.conexion.execute(f"ALTER TABLE delivery_driver_cuts ADD COLUMN {col}")
                except Exception:
                    pass
            try:
                self.conexion.execute("ALTER TABLE delivery_orders ADD COLUMN corte_id INTEGER DEFAULT 0")
            except Exception:
                pass
            self.conexion.commit()
        except Exception as exc:
            try:
                module.logger.warning("Driver history schema ensure failed: %s", exc)
            except Exception:
                pass

    def _historial_cortes_safe(self):
        """Robust driver history: shows registered cuts and delivered orders fallback."""
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor
        from PyQt5.QtWidgets import (
            QAbstractItemView,
            QDialog,
            QLabel,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QHeaderView,
        )

        Colors = getattr(module, "Colors")
        self._ensure_driver_history_schema()

        dlg = QDialog(self)
        dlg.setWindowTitle("📋 Historial de Repartidores")
        dlg.setMinimumSize(900, 500)
        lay = QVBoxLayout(dlg)

        info = QLabel("Cortes registrados y entregas por repartidor")
        info.setObjectName("subheading")
        lay.addWidget(info)

        tbl = QTableWidget()
        tbl.setColumnCount(10)
        tbl.setHorizontalHeaderLabels([
            "Tipo", "ID", "Repartidor", "Fecha", "Entregas",
            "Efectivo", "Tarjeta", "Transfer", "Entregado", "Diferencia"
        ])
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        lay.addWidget(tbl)

        rows = []
        try:
            rows = self.conexion.execute(
                """
                SELECT 'Corte' AS tipo, id, COALESCE(driver_nombre, 'Repartidor') AS driver_nombre,
                       COALESCE(fecha, turno_fin, datetime('now')) AS fecha,
                       COALESCE(entregas_total,0) AS entregas_total,
                       COALESCE(efectivo_cobrado,0) AS efectivo_cobrado,
                       COALESCE(tarjeta_cobrado,0) AS tarjeta_cobrado,
                       COALESCE(transfer_cobrado,0) AS transfer_cobrado,
                       COALESCE(efectivo_entregado,0) AS efectivo_entregado,
                       COALESCE(diferencia,0) AS diferencia
                FROM delivery_driver_cuts
                ORDER BY datetime(COALESCE(fecha, turno_fin, '1970-01-01')) DESC
                LIMIT 100
                """
            ).fetchall()
        except Exception as exc:
            try:
                module.logger.warning("Driver cut history query failed: %s", exc)
            except Exception:
                pass
            rows = []

        if not rows:
            try:
                rows = self.conexion.execute(
                    """
                    SELECT 'Entrega' AS tipo, d.id,
                           COALESCE(dr.nombre, d.responsable_entrega, 'Sin repartidor') AS driver_nombre,
                           COALESCE(d.fecha_entrega, d.fecha_actualizacion, d.fecha) AS fecha,
                           1 AS entregas_total,
                           CASE WHEN lower(COALESCE(d.pago_metodo,'')) LIKE '%efect%' THEN COALESCE(d.pago_monto,d.total,0) ELSE 0 END AS efectivo_cobrado,
                           CASE WHEN lower(COALESCE(d.pago_metodo,'')) LIKE '%tarjeta%' THEN COALESCE(d.pago_monto,d.total,0) ELSE 0 END AS tarjeta_cobrado,
                           CASE WHEN lower(COALESCE(d.pago_metodo,'')) LIKE '%transfer%' THEN COALESCE(d.pago_monto,d.total,0) ELSE 0 END AS transfer_cobrado,
                           0 AS efectivo_entregado,
                           0 AS diferencia
                    FROM delivery_orders d
                    LEFT JOIN drivers dr ON dr.id=d.driver_id
                    WHERE d.estado='entregado'
                    ORDER BY datetime(COALESCE(d.fecha_entrega, d.fecha_actualizacion, d.fecha, '1970-01-01')) DESC
                    LIMIT 100
                    """
                ).fetchall()
            except Exception as exc:
                lay.addWidget(QLabel(f"Error cargando historial de repartidores: {exc}"))
                rows = []

        tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                val = v
                if j in (5, 6, 7, 8, 9) and v is not None:
                    try:
                        val = f"${float(v):.2f}"
                    except Exception:
                        pass
                item = QTableWidgetItem(str(val) if val is not None else "")
                if j == 9 and v is not None:
                    try:
                        diff = float(v)
                        if abs(diff) <= 0.01:
                            item.setForeground(QColor(Colors.SUCCESS_BASE))
                        elif diff < 0:
                            item.setForeground(QColor(Colors.DANGER_BASE))
                        else:
                            item.setForeground(QColor(Colors.WARNING_BASE))
                    except Exception:
                        pass
                tbl.setItem(i, j, item)

        if not rows:
            empty = QLabel("No hay cortes ni entregas registradas para repartidores.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setObjectName("textMuted")
            lay.addWidget(empty)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(dlg.accept)
        lay.addWidget(btn_cerrar)
        dlg.exec_()

    if not hasattr(cls, "_safe_update_filter_tabs"):
        cls._safe_update_filter_tabs = _safe_update_filter_tabs
    if not hasattr(cls, "_safe_update_kpi"):
        cls._safe_update_kpi = _safe_update_kpi
    if not hasattr(cls, "_safe_refresh_operational_header"):
        cls._safe_refresh_operational_header = _safe_refresh_operational_header
    if not hasattr(cls, "_safe_poll_delivery_notifications"):
        cls._safe_poll_delivery_notifications = _safe_poll_delivery_notifications
    cls._ensure_driver_history_schema = _ensure_driver_history_schema
    cls._historial_cortes = _historial_cortes_safe


class _DeliveryPatchLoader(importlib.abc.Loader):
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def create_module(self, spec):
        if hasattr(self.wrapped, "create_module"):
            return self.wrapped.create_module(spec)
        return None

    def exec_module(self, module):
        self.wrapped.exec_module(module)
        _patch_delivery_module(module)


class _DeliveryPatchFinder(importlib.abc.MetaPathFinder):
    _busy = False

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "modulos.delivery" or self._busy:
            return None
        self._busy = True
        try:
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec and spec.loader and not isinstance(spec.loader, _DeliveryPatchLoader):
                spec.loader = _DeliveryPatchLoader(spec.loader)
            return spec
        finally:
            self._busy = False


if not any(isinstance(f, _DeliveryPatchFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _DeliveryPatchFinder())

# If delivery was already imported before this file completed, patch it now.
if "modulos.delivery" in sys.modules:
    _patch_delivery_module(sys.modules["modulos.delivery"])
