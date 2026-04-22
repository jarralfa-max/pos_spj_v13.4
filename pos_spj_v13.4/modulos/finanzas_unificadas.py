# modulos/finanzas_unificadas.py — SPJ POS v13.4
# ── MÓDULO UNIFICADO DE FINANZAS ─────────────────────────────────────────────
# Fusiona: Tesorería + Finanzas + Proveedores en una sola UI con pestañas
# Todos consumen core/services/finance/* (single source of truth)

import logging
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QMessageBox)
from PyQt5.QtCore import Qt

logger = logging.getLogger("spj.finanzas_unificadas")

class ModuloFinanzasUnificadas(QWidget):
    """Módulo unificado de Finanzas que integra:
    - Pestaña 1: Tesorería (flujo de caja, gastos futuros/fijos, CAPEX)
    - Pestaña 2: Finanzas (gastos, empleados, activos, nómina)
    - Pestaña 3: Proveedores (CRUD, historial, evaluación)
    
    Todas las operaciones consumen servicios unificados:
    - core/services/finance/treasury_service.py
    - core/services/enterprise/finance_service.py
    - core/services/finance/third_party_service.py
    """
    
    def __init__(self, container):
        super().__init__()
        self.container = container
        self._setup_ui()
        
    def _setup_ui(self):
        """Configura la interfaz con pestañas unificadas."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Crear widget de pestañas principal
        tabs = QTabWidget()
        tabs.setObjectName("finanzasTabs")
        tabs.setDocumentMode(True)
        
        # Estilizar pestañas para que se vean modernas
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: transparent;
            }
            QTabBar::tab {
                background-color: #1E293B;
                color: #94A3B8;
                padding: 12px 24px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background-color: #2563EB;
                color: #FFFFFF;
            }
            QTabBar::tab:hover:!selected {
                background-color: #334155;
            }
        """)
        
        # Importar módulos originales como widgets hijos
        try:
            from modulos.tesoreria import ModuloTesoreria
            tesoreria_widget = ModuloTesoreria(self.container)
            tabs.addTab(tesoreria_widget, "💰 Tesorería")
            logger.info("Pestaña Tesorería cargada exitosamente")
        except Exception as e:
            logger.error(f"Error cargando Tesorería: {e}")
            tabs.addTab(self._crear_placeholder("Tesorería"), "💰 Tesorería")
        
        try:
            from modulos.finanzas import ModuloFinanzas
            finanzas_widget = ModuloFinanzas(self.container)
            tabs.addTab(finanzas_widget, "📊 Finanzas")
            logger.info("Pestaña Finanzas cargada exitosamente")
        except Exception as e:
            logger.error(f"Error cargando Finanzas: {e}")
            tabs.addTab(self._crear_placeholder("Finanzas"), "📊 Finanzas")
        
        try:
            from modulos.proveedores import ModuloProveedores
            proveedores_widget = ModuloProveedores(self.container)
            tabs.addTab(proveedores_widget, "🏭 Proveedores")
            logger.info("Pestaña Proveedores cargada exitosamente")
        except Exception as e:
            logger.error(f"Error cargando Proveedores: {e}")
            tabs.addTab(self._crear_placeholder("Proveedores"), "🏭 Proveedores")
        
        layout.addWidget(tabs)
        
    def _crear_placeholder(self, modulo_nombre):
        """Crea un widget placeholder cuando un módulo falla al cargar."""
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignCenter)
        
        from PyQt5.QtWidgets import QLabel
        lbl = QLabel(f"⚠️ El módulo {modulo_nombre} no está disponible\n"
                    f"Por favor contacte al administrador del sistema")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("""
            color: #EF4444;
            font-size: 16px;
            font-weight: 500;
            padding: 40px;
        """)
        layout.addWidget(lbl)
        return placeholder
    
    def get_current_tab_index(self):
        """Retorna el índice de la pestaña actual."""
        for child in self.children():
            if isinstance(child, QTabWidget):
                return child.currentIndex()
        return 0
    
    def refresh_data(self):
        """Refresca los datos en todas las pestañas."""
        for child in self.children():
            if isinstance(child, QTabWidget):
                for i in range(child.count()):
                    widget = child.widget(i)
                    if hasattr(widget, '_cargar_tabla'):
                        try:
                            widget._cargar_tabla()
                        except Exception as e:
                            logger.warning(f"No se pudo refrescar {child.tabText(i)}: {e}")


# Alias para compatibilidad con main_window.py
ModuloFinanzas = ModuloFinanzasUnificadas
