
# modulos/base.py
from modulos.spj_styles import spj_btn, apply_btn_styles
from PyQt5.QtWidgets import QWidget, QMessageBox, QStyle
from PyQt5.QtGui import QIcon
import os
import sqlite3
import config
from typing import Optional, Dict, Callable, List, Any, Union
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ModuloBase(QWidget):
    """Clase base para todos los módulos de la aplicación que maneja funcionalidades comunes y conexión a BD."""

    def __init__(self, conexion: sqlite3.Connection, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.conexion = conexion
        self.main_window = parent  # Referencia a la ventana principal
        self.usuario_actual: Optional[str] = None
        self.rol_usuario: Optional[str] = None
        self.sesion_iniciada: bool = False
        self._callbacks_actualizacion: Dict[str, Callable] = {}
        
        # Si no se proporciona conexión, intentar obtenerla del parent
        if self.conexion is None and hasattr(parent, 'conexion'):
            self.conexion = parent.conexion

    def inicializar_bd(self) -> bool:
        """
        Verifica la conexión a la base de datos.
        Nota: La creación de tablas y sembrado de datos ahora es manejada
        exclusivamente por el motor de migraciones central.
        """
        try:
            cursor = self.conexion.cursor()
            cursor.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Error verificando BD: {e}")
            return False

    def obtener_icono(self, nombre_icono: str) -> QIcon:
        """Obtiene un icono desde la carpeta de recursos o usa iconos del sistema como fallback."""
        # Primero intentar cargar desde archivo en el directorio actual
        if os.path.exists(nombre_icono):
            return QIcon(nombre_icono)
        
        # Intentar en subcarpeta 'icons' si existe
        ruta_icono = os.path.join('icons', nombre_icono)
        if os.path.exists(ruta_icono):
            return QIcon(ruta_icono)
        
        # Si no existe el archivo, usar iconos del sistema como fallback
        iconos_sistema = {
            "search.png":   QStyle.SP_FileDialogContentsView,
            "filter.png":   QStyle.SP_FileDialogDetailedView,
            "add.png":      QStyle.SP_FileDialogNewFolder,
            "edit.png":     QStyle.SP_FileDialogContentsView,
            "delete.png":   QStyle.SP_TrashIcon,
            "history.png":  QStyle.SP_FileDialogDetailedView,
            "card.png":     QStyle.SP_FileDialogInfoView,
            "payment.png":  QStyle.SP_DialogApplyButton,
            "refresh.png":  QStyle.SP_BrowserReload,
            "list.png":     QStyle.SP_FileDialogListView,
            "transfer.png": QStyle.SP_FileDialogBack,
            "save.png":     QStyle.SP_DialogSaveButton,
            "cancel.png":   QStyle.SP_DialogCancelButton,
            "print.png":    QStyle.SP_ComputerIcon,
            "config.png":   QStyle.SP_ComputerIcon,
            "security.png": QStyle.SP_MessageBoxWarning,
        }

        if nombre_icono in iconos_sistema:
            return self.style().standardIcon(iconos_sistema[nombre_icono])

        # Icono vacío sin ruido en el log
        logger.debug("Icono '%s' no encontrado, usando QIcon vacío", nombre_icono)
        return QIcon()

    def mostrar_mensaje(self, titulo: str, mensaje: str, 
                       icono=QMessageBox.Information, 
                       botones=QMessageBox.Ok) -> int:
        """Muestra un mensaje al usuario de forma segura."""
        try:
            msg = QMessageBox(self)
            msg.setWindowTitle(titulo)
            msg.setText(mensaje)
            msg.setIcon(icono)
            msg.setStandardButtons(botones)
            return msg.exec_()
        except Exception as e:
            logger.error(f"Error al mostrar mensaje: {e}")
            # Fallback: mostrar en consola
            print(f"[{titulo}] {mensaje}")
            return QMessageBox.Ok

    def ejecutar_consulta(self, consulta: str, parametros: tuple = None) -> Optional[sqlite3.Cursor]:
        """Ejecuta una consulta SQL de forma segura."""
        try:
            cursor = self.conexion.cursor()
            if parametros:
                cursor.execute(consulta, parametros)
            else:
                cursor.execute(consulta)
            return cursor
        except sqlite3.Error as e:
            self.mostrar_mensaje("Error BD", f"Error en consulta: {str(e)}", QMessageBox.Critical)
            return None

    def insertar_registro(self, tabla: str, datos: Dict[str, Any]) -> Optional[int]:
        """Inserta un registro en una tabla."""
        try:
            columnas = ', '.join(datos.keys())
            placeholders = ', '.join(['?' for _ in datos])
            valores = list(datos.values())
            
            consulta = f"INSERT INTO {tabla} ({columnas}) VALUES ({placeholders})"
            cursor = self.ejecutar_consulta(consulta, valores)
            
            if cursor:
                self.conexion.commit()
                return cursor.lastrowid
            return None
        except sqlite3.Error as e:
            self.conexion.rollback()
            self.mostrar_mensaje("Error BD", f"Error al insertar: {str(e)}", QMessageBox.Critical)
            return None

    def actualizar_registro(self, tabla: str, datos: Dict[str, Any], where: str, where_params: tuple = None) -> bool:
        """Actualiza un registro en una tabla."""
        try:
            sets = ', '.join([f"{k} = ?" for k in datos.keys()])
            valores = list(datos.values())
            
            if where_params:
                valores.extend(where_params)
            
            consulta = f"UPDATE {tabla} SET {sets} WHERE {where}"
            cursor = self.ejecutar_consulta(consulta, valores)
            
            if cursor:
                self.conexion.commit()
                return cursor.rowcount > 0
            return False
        except sqlite3.Error as e:
            self.conexion.rollback()
            self.mostrar_mensaje("Error BD", f"Error al actualizar: {str(e)}", QMessageBox.Critical)
            return False

    def set_usuario_actual(self, usuario: str, rol: str):
        """Establece el usuario actual para el módulo"""
        self.usuario_actual = usuario
        self.rol_usuario = rol
        self.sesion_iniciada = True

    def obtener_usuario_actual(self) -> str:
        """Obtiene el usuario actual para registrar en movimientos"""
        return self.usuario_actual if self.usuario_actual else "Sistema"

    def registrar_actualizacion(self, tipo_evento: str, detalles=None, usuario=None):
        """Registra actualizaciones del módulo en los logs."""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            usuario_info = usuario if usuario else self.usuario_actual or "Sistema"
            modulo = self.__class__.__name__
            
            mensaje = f"[{timestamp}] [{usuario_info}] [{modulo}] Evento: {tipo_evento}"
            
            if detalles:
                if isinstance(detalles, dict):
                    detalles_str = ", ".join([f"{k}:{v}" for k, v in detalles.items()])
                    mensaje += f" - {detalles_str}"
                else:
                    mensaje += f" - {detalles}"
            
            logger.info(mensaje)
            
            # Guardar en archivo de log para compatibilidad con el sistema anterior
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
                
            with open(f"{log_dir}/sistema_actualizaciones.log", "a", encoding="utf-8") as f:
                f.write(mensaje + "\n")
                
        except Exception as e:
            logger.error(f"Error al registrar actualización: {e}")

    def limpiar(self):
        """Limpia recursos del módulo"""
        self._callbacks_actualizacion.clear()

    def closeEvent(self, event):
        """Maneja el cierre del módulo"""
        self.limpiar()
        event.accept()