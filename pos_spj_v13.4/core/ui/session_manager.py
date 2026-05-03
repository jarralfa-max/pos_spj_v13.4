
# core/ui/session_manager.py
from __future__ import annotations
import logging
from typing import Optional, List
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QWidget

logger = logging.getLogger("spj.ui.session")

class SessionManager(QObject):
    sesion_iniciada = pyqtSignal(dict)
    sesion_cerrada  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.usuario: Optional[str] = None
        self.rol: Optional[str]     = None
        self.sucursal_id: int       = 1
        self.sucursal_nombre: str   = "Principal"
        self._modulos: List[QWidget]= []

    def registrar_modulo(self, w):
        self._modulos.append(w)

    def iniciar(self, usuario, rol, sucursal_id=1, sucursal_nombre="Principal", nombre_completo=""):
        self.usuario         = usuario
        self.rol             = rol
        self.sucursal_id     = sucursal_id
        self.sucursal_nombre = sucursal_nombre
        datos = {"usuario":usuario,"rol":rol,"sucursal_id":sucursal_id,
                 "sucursal_nombre":sucursal_nombre,"nombre_completo":nombre_completo}
        self._propagar(datos)
        self.sesion_iniciada.emit(datos)
        logger.info("Sesion: %s (%s) @ %s", usuario, rol, sucursal_nombre)

    def cerrar(self):
        self.usuario = self.rol = None
        self._propagar(None)
        self.sesion_cerrada.emit()

    def _propagar(self, datos):
        for m in self._modulos:
            if datos:
                for fn,args in [("set_sesion",[datos["usuario"],datos["rol"]]),
                                 ("set_usuario_actual",[datos["usuario"],datos["rol"]])]:
                    if hasattr(m,fn):
                        try: getattr(m,fn)(*args)
                        except Exception: pass
            else:
                if hasattr(m,"cerrar_sesion"):
                    try: m.cerrar_sesion()
                    except Exception: pass

    @property
    def activa(self): return self.usuario is not None

    @property
    def es_admin(self): return (self.rol or "").lower() in ("admin","administrador","gerente")
