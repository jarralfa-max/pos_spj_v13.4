
# modulos/config_interfaz.py
from modulos.spj_styles import spj_btn, apply_btn_styles
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QFormLayout, QDoubleSpinBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QDialog, QDialogButtonBox, QHeaderView,
    QAbstractItemView, QFrame, QSplitter, QGridLayout, QListWidget,
    QListWidgetItem, QCompleter, QDateEdit, QTimeEdit, QTabWidget,
    QRadioButton, QButtonGroup, QCheckBox, QSpinBox, QTextEdit, QMenu,
    QAction, QToolBar, QStatusBar, QProgressBar, QSlider, QDial,
    QCalendarWidget, QColorDialog, QFontDialog, QFileDialog, QInputDialog,
    QErrorMessage, QProgressDialog, QSplashScreen, QSystemTrayIcon,
    QStyleFactory, QApplication, QSizePolicy, QStackedWidget, QScrollArea
)
from PyQt5.QtCore import Qt

class ModuloConfigUI(QWidget):
    """
    Panel de Personalización Visual (Temas, Fuentes, Densidad).
    """
    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container
        self.init_ui()
        try:
            self.cargar_preferencias_actuales()
        except Exception as _e:
            import logging; logging.getLogger(__name__).debug("cargar prefs: %s", _e)

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        """Recibe el usuario activo al cambiar de sesión."""
        self.usuario_actual = usuario
        self.rol_actual = rol

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        """Recibe la sucursal activa."""
        self.sucursal_id = sucursal_id

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        lbl_titulo = QLabel("🎨 Personalización de la Interfaz (UI)")
        lbl_titulo.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(lbl_titulo)
        
        panel_principal = QHBoxLayout()
        
        # --- COLUMNA IZQUIERDA: CONTROLES ---
        grupo_controles = QGroupBox("Parámetros de Diseño")
        form = QFormLayout(grupo_controles)
        
        self.cmb_tema = QComboBox()
        self.cmb_tema.addItems(self.container.theme_service.palettes.keys())
        
        self.cmb_densidad = QComboBox()
        self.cmb_densidad.addItems(self.container.theme_service.densities.keys())
        
        self.spin_font = QSpinBox()
        self.spin_font.setRange(8, 24)
        self.spin_font.setSuffix(" pt")
        
        self.spin_icon = QSpinBox()
        self.spin_icon.setRange(16, 64)
        self.spin_icon.setSingleStep(4)
        self.spin_icon.setSuffix(" px")
        
        form.addRow("Tema de Color:", self.cmb_tema)
        form.addRow("Densidad (Espaciado):", self.cmb_densidad)
        form.addRow("Tamaño de Letra:", self.spin_font)
        form.addRow("Tamaño de Iconos:", self.spin_icon)
        
        btn_aplicar = QPushButton("💾 Guardar y Aplicar Cambios")
        btn_aplicar.setObjectName("successBtn")
        btn_aplicar.clicked.connect(self.aplicar_cambios)
        form.addRow("", btn_aplicar)
        
        panel_principal.addWidget(grupo_controles, 1)
        
        # --- COLUMNA DERECHA: VISTA PREVIA ---
        grupo_preview = QGroupBox("Vista Previa (Demostración)")
        grupo_preview.setObjectName("panel") # Para que tome el estilo QSS
        preview_layout = QVBoxLayout(grupo_preview)
        
        lbl_demo = QLabel("Así se verá tu sistema con esta configuración.")
        txt_demo = QLineEdit()
        txt_demo.setPlaceholderText("Campo de texto de prueba...")
        btn_demo1 = QPushButton("Botón Principal"); btn_demo1.setObjectName("primaryBtn")
        btn_demo2 = QPushButton("Botón Peligro");   btn_demo2.setObjectName("dangerBtn")
        
        tabla_demo = QTableWidget(3, 3)
        tabla_demo.setHorizontalHeaderLabels(["Columna 1", "Columna 2", "Columna 3"])
        
        preview_layout.addWidget(lbl_demo)
        preview_layout.addWidget(txt_demo)
        
        h_btns = QHBoxLayout()
        h_btns.addWidget(btn_demo1)
        h_btns.addWidget(btn_demo2)
        preview_layout.addLayout(h_btns)
        
        preview_layout.addWidget(tabla_demo)
        
        panel_principal.addWidget(grupo_preview, 2)
        layout.addLayout(panel_principal)

    def cargar_preferencias_actuales(self):
        try:
            prefs = self.container.theme_service.get_user_preferences()
            self.cmb_tema.setCurrentText(prefs.get('theme', 'Light'))
            self.cmb_densidad.setCurrentText(prefs.get('density', 'Normal'))
            self.spin_font.setValue(int(prefs.get('font_size', 12)))
            self.spin_icon.setValue(int(prefs.get('icon_size', 24)))
        except Exception:
            pass

    def aplicar_cambios(self):
        """Guarda en BD y recompila el QSS en tiempo real."""
        tema = self.cmb_tema.currentText()
        densidad = self.cmb_densidad.currentText()
        font = str(self.spin_font.value())
        icon = str(self.spin_icon.value())
        
        try:
            # 1. Guardar en Base de Datos
            self.container.theme_service.save_preferences(tema, densidad, font, icon)
            
            # 2. 🚀 Aplicar a toda la aplicación SIN REINICIAR
            # Accedemos a la instancia global de QApplication
            app = QApplication.instance()
            if app:
                self.container.theme_service.apply_to_app(app)
                
            QMessageBox.information(self, "Éxito", "¡Tema aplicado correctamente a todo el sistema!")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo aplicar el tema: {e}")
            