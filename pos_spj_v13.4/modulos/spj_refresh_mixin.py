# modulos/spj_refresh_mixin.py — SPJ POS v13.2
"""
Mixin de auto-refresco vía EventBus.
Los módulos que heredan este mixin se actualizan automáticamente
cuando otros módulos publican cambios de datos.

USO:
    class ModuloClientes(QWidget, RefreshMixin):
        def __init__(self, container, parent=None):
            super().__init__(parent)
            self._init_refresh(container, [VENTA_COMPLETADA, PRODUCTO_CREADO])

        def _on_refresh(self, event_type: str, data: dict):
            self.cargar_clientes()   # método que recarga datos
"""
from __future__ import annotations
from typing import List
import logging
from PyQt5.QtCore import QTimer

logger = logging.getLogger("spj.refresh_mixin")


class RefreshMixin:
    """
    Mixin que suscribe al módulo al EventBus.
    El refresco tiene un debounce de 500ms para evitar múltiples recargas
    cuando varios eventos llegan en ráfaga.

    También provee wrappers seguros para cargas auxiliares. Estos wrappers no
    reemplazan reglas de negocio: solo evitan que un error secundario de KPI,
    pestañas, header o notificaciones tumbe la carga principal de un módulo.
    """

    def _init_refresh(
        self,
        container,
        event_types: List[str],
        debounce_ms: int = 500,
    ) -> None:
        self._refresh_container   = container
        self._refresh_event_types = event_types
        self._refresh_debounce_ms = debounce_ms
        self._refresh_debounce    = None  # Created lazily in main thread
        self._pending_event: str  = ""
        self._pending_data: dict  = {}
        self._subscribe_events()

    def _ensure_timer(self) -> None:
        """Create the debounce timer in the Qt main thread (lazy)."""
        if self._refresh_debounce is None:
            self._refresh_debounce = QTimer()
            self._refresh_debounce.setSingleShot(True)
            self._refresh_debounce.setInterval(self._refresh_debounce_ms)
            self._refresh_debounce.timeout.connect(self._do_refresh)

    def _subscribe_events(self) -> None:
        try:
            from core.events.event_bus import get_bus
            bus = get_bus()
            for evt in self._refresh_event_types:
                bus.subscribe(evt, self._on_event_received)
            logger.debug("RefreshMixin subscribed to: %s", self._refresh_event_types)
        except Exception as e:
            logger.debug("RefreshMixin subscribe: %s", e)

    def _on_event_received(self, data: dict) -> None:
        """
        Recibe el evento (puede llegar desde hilo background del EventBus).
        Usa QTimer.singleShot(0) para despachar el refresco al hilo Qt principal.
        """
        event_type = data.get("event_type", "")
        self._pending_event = event_type
        self._pending_data  = data
        try:
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, self._schedule_refresh)
        except Exception:
            pass

    def _schedule_refresh(self) -> None:
        """Called in Qt main thread — creates timer if needed, then starts debounce."""
        self._ensure_timer()
        if not self._refresh_debounce.isActive():
            self._refresh_debounce.start()

    def _do_refresh(self) -> None:
        """Ejecuta el refresco real. No llama directamente — usa el debounce."""
        try:
            self._on_refresh(self._pending_event, self._pending_data)
        except Exception as e:
            logger.debug("RefreshMixin _do_refresh: %s", e)

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """
        Override en la subclase para definir qué hacer al recibir el evento.
        Por defecto busca un método 'refresh()' o 'cargar_datos()'.
        """
        for method_name in ('refresh', 'cargar_datos', 'cargar_todo',
                             'actualizar', 'reload', '_refresh_all'):
            if hasattr(self, method_name):
                try:
                    getattr(self, method_name)()
                    return
                except Exception as e:
                    logger.debug("RefreshMixin auto-refresh %s: %s", method_name, e)
                    return

    def _safe_call_auxiliary(self, method_name: str, *args, **kwargs):
        """Ejecuta una carga auxiliar sin romper la carga principal."""
        method = getattr(self, method_name, None)
        if not callable(method):
            logger.debug("Auxiliary method missing: %s", method_name)
            return None
        try:
            return method(*args, **kwargs)
        except Exception as exc:
            logger.warning("Auxiliary UI load failed in %s: %s", method_name, exc)
            try:
                setattr(self, "_last_aux_error", str(exc))
            except Exception:
                pass
            return None

    def _safe_update_filter_tabs(self, pedidos, counts_estado):
        return self._safe_call_auxiliary("_update_filter_tabs", pedidos, counts_estado)

    def _safe_update_kpi(self, pedidos):
        return self._safe_call_auxiliary("_update_kpi", pedidos)

    def _safe_refresh_operational_header(self):
        return self._safe_call_auxiliary("_refresh_operational_header")

    def _safe_poll_delivery_notifications(self):
        return self._safe_call_auxiliary("_poll_delivery_notifications")
