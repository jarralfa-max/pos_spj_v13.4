"""
Módulo de Diagnóstico del Sistema SPJ POS
Detecta módulos fallidos, dependencias faltantes y problemas de configuración
"""
import sys
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QGroupBox, QScrollArea, QWidget, QMessageBox,
    QProgressBar, QApplication
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QTextCursor

logger = logging.getLogger("spj.diagnostico")


class DiagnosticoSistema(QDialog):
    """Diálogo de diagnóstico del sistema con interfaz gráfica"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔧 Diagnóstico del Sistema")
        self.setMinimumSize(800, 600)
        self.setModal(True)
        
        # Datos del diagnóstico
        self.modulos_fallidos: List[Dict] = []
        self.dependencias_faltantes: List[str] = []
        self.advertencias: List[str] = []
        self.estado_general = "OK"
        
        self._configurar_ui()
        self._ejecutar_diagnostico()
    
    def _configurar_ui(self):
        """Configura la interfaz de usuario"""
        layout_principal = QVBoxLayout()
        layout_principal.setSpacing(15)
        layout_principal.setContentsMargins(20, 20, 20, 20)
        
        # Encabezado
        lbl_titulo = QLabel("🔍 Diagnóstico del Sistema SPJ POS")
        lbl_titulo.setFont(QFont("Segoe UI", 16, QFont.Bold))
        lbl_titulo.setObjectName("headingLabel")
        layout_principal.addWidget(lbl_titulo)
        
        # Barra de progreso
        self.barra_progreso = QProgressBar()
        self.barra_progreso.setRange(0, 100)
        self.barra_progreso.setValue(0)
        self.barra_progreso.setObjectName("standardProgressBar")
        layout_principal.addWidget(self.barra_progreso)
        
        # Estado general
        self.lbl_estado = QLabel("Estado: Analizando...")
        self.lbl_estado.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.lbl_estado.setStyleSheet("padding: 10px; background: #f39c12; color: white; border-radius: 5px;")
        layout_principal.addWidget(self.lbl_estado)
        
        # Área con scroll para resultados
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: 1px solid #bdc3c7; border-radius: 5px;")
        
        self.contenido_widget = QWidget()
        self.layout_contenido = QVBoxLayout()
        self.layout_contenido.setSpacing(10)
        self.contenido_widget.setLayout(self.layout_contenido)
        scroll.setWidget(self.contenido_widget)
        
        layout_principal.addWidget(scroll, stretch=1)
        
        # Botones de acción
        layout_botones = QHBoxLayout()
        
        btn_copiar = QPushButton("📋 Copiar Reporte")
        btn_copiar.setObjectName("secondaryBtn")
        btn_copiar.clicked.connect(self._copiar_reporte)
        layout_botones.addWidget(btn_copiar)
        
        btn_instalar = QPushButton("📦 Instalar Dependencias")
        btn_instalar.setObjectName("primaryBtn")
        btn_instalar.clicked.connect(self._instalar_dependencias)
        layout_botones.addWidget(btn_instalar)
        
        btn_actualizar = QPushButton("🔄 Actualizar")
        btn_actualizar.setObjectName("secondaryBtn")
        btn_actualizar.clicked.connect(self._ejecutar_diagnostico)
        layout_botones.addWidget(btn_actualizar)
        
        btn_cerrar = QPushButton("✅ Cerrar")
        btn_cerrar.setObjectName("successBtn")
        btn_cerrar.clicked.connect(self.accept)
        layout_botones.addWidget(btn_cerrar)
        
        layout_principal.addLayout(layout_botones)
        
        self.setLayout(layout_principal)
    
    def _ejecutar_diagnostico(self):
        """Ejecuta el diagnóstico completo"""
        self.barra_progreso.setValue(10)
        QApplication.processEvents()
        
        # Limpiar resultados anteriores
        self._limpiar_resultados()
        
        # Verificar módulos
        self.barra_progreso.setValue(30)
        QApplication.processEvents()
        self._verificar_modulos()
        
        # Verificar dependencias
        self.barra_progreso.setValue(60)
        QApplication.processEvents()
        self._verificar_dependencias()
        
        # Verificar configuración
        self.barra_progreso.setValue(80)
        QApplication.processEvents()
        self._verificar_configuracion()
        
        # Finalizar
        self.barra_progreso.setValue(100)
        QApplication.processEvents()
        self._actualizar_estado()
        self._mostrar_resultados()
    
    def _limpiar_resultados(self):
        """Limpia los resultados anteriores"""
        self.modulos_fallidos = []
        self.dependencias_faltantes = []
        self.advertencias = []
        
        # Limpiar widgets del contenido
        while self.layout_contenido.count():
            widget = self.layout_contenido.takeAt(0).widget()
            if widget:
                widget.deleteLater()
    
    def _verificar_modulos(self):
        """Verifica el estado de los módulos principales"""
        try:
            from interfaz.main_window import MainWindow
            
            # Lista de módulos críticos a verificar
            modulos_criticos = [
                ("Ventas", "modulos.ventas"),
                ("Caja", "modulos.caja"),
                ("Inventario", "modulos.inventario"),
                ("Productos", "modulos.productos"),
                ("Clientes", "modulos.clientes"),
                ("Finanzas", "modulos.finanzas"),
                ("Reportes", "modulos.reportes"),
            ]
            
            for nombre, modulo_path in modulos_criticos:
                try:
                    __import__(modulo_path)
                    logger.info(f"Módulo {nombre}: OK")
                except ImportError as e:
                    self.modulos_fallidos.append({
                        "nombre": nombre,
                        "error": str(e),
                        "tipo": "ImportError"
                    })
                    logger.error(f"Módulo {nombre}: FALLIDO - {e}")
                except Exception as e:
                    self.modulos_fallidos.append({
                        "nombre": nombre,
                        "error": str(e),
                        "tipo": type(e).__name__
                    })
                    logger.error(f"Módulo {nombre}: ERROR - {e}")
                    
        except Exception as e:
            logger.error(f"Error verificando módulos: {e}")
            self.advertencias.append(f"Error al verificar módulos: {e}")
    
    def _verificar_dependencias(self):
        """Verifica dependencias externas críticas"""
        dependencias_requeridas = [
            ("PyQt5", "PyQt5"),
            ("reportlab", "reportlab"),
            ("openpyxl", "openpyxl"),
            ("PIL/Pillow", "PIL"),
            ("pandas", "pandas"),
            ("numpy", "numpy"),
            ("matplotlib", "matplotlib"),
        ]
        
        for nombre, import_name in dependencias_requeridas:
            try:
                __import__(import_name)
            except ImportError:
                self.dependencias_faltantes.append(nombre)
                logger.warning(f"Dependencia faltante: {nombre}")
    
    def _verificar_configuracion(self):
        """Verifica archivos de configuración y temas"""
        try:
            # Verificar tema por defecto
            from ui.themes.theme_engine import ThemeEngine
            engine = ThemeEngine()
            if not engine.get_available_themes():
                self.advertencias.append("No hay temas disponibles")
        except Exception as e:
            self.advertencias.append(f"Error en ThemeEngine: {e}")
        
        try:
            # Verificar base de datos
            import sqlite3
            conn = sqlite3.connect(":memory:")
            conn.close()
        except Exception as e:
            self.advertencias.append(f"Error con SQLite: {e}")
    
    def _actualizar_estado(self):
        """Actualiza el estado general basado en los resultados"""
        if self.modulos_fallidos or self.dependencias_faltantes:
            self.estado_general = "CRÍTICO"
            self.lbl_estado.setText(f"⚠️ Estado: {self.estado_general} - Se requieren acciones")
            self.lbl_estado.setStyleSheet(
                "padding: 10px; background: #e74c3c; color: white; border-radius: 5px;"
            )
        elif self.advertencias:
            self.estado_general = "ADVERTENCIA"
            self.lbl_estado.setText(f"⚡ Estado: {self.estado_general} - Hay advertencias")
            self.lbl_estado.setStyleSheet(
                "padding: 10px; background: #f39c12; color: white; border-radius: 5px;"
            )
        else:
            self.estado_general = "OK"
            self.lbl_estado.setText("✅ Estado: ÓPTIMO - Todo funciona correctamente")
            self.lbl_estado.setStyleSheet(
                "padding: 10px; background: #27ae60; color: white; border-radius: 5px;"
            )
    
    def _mostrar_resultados(self):
        """Muestra los resultados en la interfaz"""
        # Sección: Módulos Fallidos
        if self.modulos_fallidos:
            grupo_modulos = QGroupBox(f"❌ Módulos con Problemas ({len(self.modulos_fallidos)})")
            grupo_modulos.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    border: 2px solid #e74c3c;
                    border-radius: 5px;
                    margin-top: 10px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                    color: #e74c3c;
                }
            """)
            layout_modulos = QVBoxLayout()
            
            for modulo in self.modulos_fallidos:
                lbl = QLabel(f"<b>{modulo['nombre']}</b>: {modulo['error']}")
                lbl.setWordWrap(True)
                lbl.setStyleSheet("padding: 5px; background: #fadbd8; border-left: 3px solid #e74c3c;")
                layout_modulos.addWidget(lbl)
            
            grupo_modulos.setLayout(layout_modulos)
            self.layout_contenido.addWidget(grupo_modulos)
        
        # Sección: Dependencias Faltantes
        if self.dependencias_faltantes:
            grupo_deps = QGroupBox(f"📦 Dependencias Faltantes ({len(self.dependencias_faltantes)})")
            grupo_deps.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    border: 2px solid #f39c12;
                    border-radius: 5px;
                    margin-top: 10px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                    color: #f39c12;
                }
            """)
            layout_deps = QVBoxLayout()
            
            for dep in self.dependencias_faltantes:
                lbl = QLabel(f"• {dep}")
                lbl.setStyleSheet("padding: 5px; font-size: 13px;")
                layout_deps.addWidget(lbl)
            
            grupo_deps.setLayout(layout_deps)
            self.layout_contenido.addWidget(grupo_deps)
        
        # Sección: Advertencias
        if self.advertencias:
            grupo_advertencias = QGroupBox(f"⚠️ Advertencias ({len(self.advertencias)})")
            grupo_advertencias.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    border: 2px solid #f39c12;
                    border-radius: 5px;
                    margin-top: 10px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                    color: #f39c12;
                }
            """)
            layout_advertencias = QVBoxLayout()
            
            for adv in self.advertencias:
                lbl = QLabel(f"• {adv}")
                lbl.setWordWrap(True)
                lbl.setStyleSheet("padding: 5px; font-size: 13px;")
                layout_advertencias.addWidget(lbl)
            
            grupo_advertencias.setLayout(layout_advertencias)
            self.layout_contenido.addWidget(grupo_advertencias)
        
        # Si todo está bien
        if not self.modulos_fallidos and not self.dependencias_faltantes and not self.advertencias:
            lbl_ok = QLabel("✅ Todos los sistemas operan correctamente")
            lbl_ok.setFont(QFont("Segoe UI", 14, QFont.Bold))
            lbl_ok.setAlignment(Qt.AlignCenter)
            lbl_ok.setStyleSheet("padding: 20px; color: #27ae60;")
            self.layout_contenido.addWidget(lbl_ok)
    
    def _copiar_reporte(self):
        """Copia el reporte al portapapeles"""
        reporte = self._generar_reporte_texto()
        clipboard = QApplication.clipboard()
        clipboard.setText(reporte)
        
        QMessageBox.information(
            self,
            "Reporte Copiado",
            "El reporte ha sido copiado al portapapeles.\nPuedes pegarlo en un email o documento."
        )
    
    def _instalar_dependencias(self):
        """Intenta instalar las dependencias faltantes"""
        if not self.dependencias_faltantes:
            QMessageBox.information(
                self,
                "Sin Dependencias Faltantes",
                "No hay dependencias faltantes que instalar."
            )
            return
        
        mensaje = (
            "Se instalarán las siguientes dependencias:\n\n"
            + "\n".join(f"• {dep}" for dep in self.dependencias_faltantes)
            + "\n\n¿Deseas continuar?"
        )
        
        respuesta = QMessageBox.question(
            self,
            "Instalar Dependencias",
            mensaje,
            QMessageBox.Yes | QMessageBox.No
        )
        
        if respuesta == QMessageBox.Yes:
            try:
                import subprocess
                paquetes = [dep.lower().replace("pil/pillow", "pillow").replace("/", "-") 
                           for dep in self.dependencias_faltantes]
                
                cmd = [sys.executable, "-m", "pip", "install"] + paquetes
                
                QMessageBox.information(
                    self,
                    "Instalando...",
                    f"Ejecutando: {' '.join(cmd)}\n\nEsto puede tomar unos minutos."
                )
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                
                if result.returncode == 0:
                    QMessageBox.information(
                        self,
                        "✅ Instalación Completada",
                        "Las dependencias se instalaron correctamente.\nReinicia la aplicación para aplicar los cambios."
                    )
                    self._ejecutar_diagnostico()  # Re-ejecutar diagnóstico
                else:
                    QMessageBox.warning(
                        self,
                        "⚠️ Error en Instalación",
                        f"No se pudieron instalar algunas dependencias:\n{result.stderr}"
                    )
                    
            except subprocess.TimeoutExpired:
                QMessageBox.warning(
                    self,
                    "⏱️ Tiempo Agotado",
                    "La instalación tardó demasiado. Intenta manualmente desde la terminal."
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "❌ Error",
                    f"Error al instalar dependencias:\n{str(e)}"
                )
    
    def _generar_reporte_texto(self) -> str:
        """Genera un reporte en texto plano"""
        linea = "=" * 60
        reporte = [
            linea,
            "REPORTE DE DIAGNÓSTICO - SPJ POS",
            f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Estado: {self.estado_general}",
            linea,
            "",
        ]
        
        if self.modulos_fallidos:
            reporte.append("MÓDULOS CON PROBLEMAS:")
            for modulo in self.modulos_fallidos:
                reporte.append(f"  ❌ {modulo['nombre']}: {modulo['error']}")
            reporte.append("")
        
        if self.dependencias_faltantes:
            reporte.append("DEPENDENCIAS FALTANTES:")
            for dep in self.dependencias_faltantes:
                reporte.append(f"  📦 {dep}")
            reporte.append("")
        
        if self.advertencias:
            reporte.append("ADVERTENCIAS:")
            for adv in self.advertencias:
                reporte.append(f"  ⚠️ {adv}")
            reporte.append("")
        
        if not any([self.modulos_fallidos, self.dependencias_faltantes, self.advertencias]):
            reporte.append("✅ Todos los sistemas operan correctamente")
        
        reporte.append(linea)
        
        return "\n".join(reporte)


def mostrar_diagnostico(parent=None):
    """Función utilitaria para mostrar el diagnóstico"""
    dlg = DiagnosticoSistema(parent)
    return dlg.exec_()
