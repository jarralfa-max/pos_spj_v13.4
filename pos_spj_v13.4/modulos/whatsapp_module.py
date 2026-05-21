# modulos/whatsapp_module.py — shim de compatibilidad
"""Re-exporta ModuloWhatsApp desde el paquete modulos.whatsapp."""
from modulos.whatsapp.whatsapp_module import ModuloWhatsApp  # noqa: F401

__all__ = ["ModuloWhatsApp"]
