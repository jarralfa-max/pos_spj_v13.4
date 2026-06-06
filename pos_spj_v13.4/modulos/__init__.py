"""Compatibilidad de módulos UI del POS."""

import logging

logger = logging.getLogger("spj.modulos.compat")


def _patch_qcompleter_minimum_contents_length() -> None:
    """Evita crash por llamada legacy a QCompleter.setMinimumContentsLength.

    En PyQt5, QCompleter no tiene este método; pertenece a QComboBox. El módulo
    de ventas ya controla sugerencias desde 1 carácter con su propia validación,
    por lo que aquí sólo se conserva compatibilidad sin cambiar layout ni UX.
    """
    try:
        from PyQt5.QtWidgets import QCompleter
    except Exception:
        return

    if hasattr(QCompleter, "setMinimumContentsLength"):
        return

    def _set_minimum_contents_length(self, length: int) -> None:
        try:
            self._spj_minimum_contents_length = int(length or 0)
        except Exception:
            self._spj_minimum_contents_length = 0

    QCompleter.setMinimumContentsLength = _set_minimum_contents_length


def _patch_missing_merma_click_logger() -> None:
    """Compatibilidad para builds donde ModuloMerma conecta un logger removido.

    Algunas versiones de ``modulos.merma`` aún conectan la señal privada
    ``product_selector._results.itemClicked`` contra
    ``self._log_producto_result_click``. Si el método ya fue eliminado, PyQt
    falla al instanciar el módulo con AttributeError antes de mostrar la UI.

    Este parche conserva compatibilidad agregando un no-op seguro en QWidget.
    La selección real sigue pasando por ``SearchSelector.selected`` y
    ``ModuloMerma._on_producto_selected``.
    """
    try:
        from PyQt5.QtWidgets import QWidget
    except Exception:
        return

    if hasattr(QWidget, "_log_producto_result_click"):
        return

    def _log_producto_result_click(self, item) -> None:
        try:
            text = item.text() if item is not None and hasattr(item, "text") else ""
            logger.debug("[MERMA] click legacy ignorado text=%r", text)
        except Exception:
            logger.debug("[MERMA] click legacy ignorado")

    QWidget._log_producto_result_click = _log_producto_result_click


_patch_qcompleter_minimum_contents_length()
_patch_missing_merma_click_logger()
