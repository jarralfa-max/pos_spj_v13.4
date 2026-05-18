"""
application/purchases/states.py
────────────────────────────────
Estados documentales para el flujo de compras ERP.

Diseñados para Phase 3 (PR/PO) pero declarados aquí para que el resto del
sistema pueda importarlos desde Fase 2 sin depender de la implementación.
"""
from __future__ import annotations
from enum import Enum


class DocumentType(str, Enum):
    """Tipo de documento de compra."""
    DIRECT = "DIRECT"    # Compra directa (flujo actual, sin PR/PO)
    PR     = "PR"        # Purchase Request — solo documental
    PO     = "PO"        # Purchase Order — convierte PR aprobada


class PRState(str, Enum):
    """Estados del ciclo de vida de una Purchase Request."""
    BORRADOR              = "BORRADOR"
    PENDIENTE_APROBACION  = "PENDIENTE_APROBACION"
    APROBADA              = "APROBADA"
    RECHAZADA             = "RECHAZADA"
    CONVERTIDA_A_PO       = "CONVERTIDA_A_PO"
    CANCELADA             = "CANCELADA"


class POState(str, Enum):
    """Estados del ciclo de vida de una Purchase Order."""
    ABIERTA          = "ABIERTA"
    PARA_RECEPCION   = "PARA_RECEPCION"   # Enviada al área de recepción, pendiente de recibir
    PARCIAL          = "PARCIAL"
    RECIBIDA         = "RECIBIDA"
    CERRADA          = "CERRADA"
    CANCELADA        = "CANCELADA"


class DirectPurchaseState(str, Enum):
    """Estados del flujo de compra directa (legacy compatible)."""
    COMPLETADA = "completada"
    CREDITO    = "credito"
    PARCIAL    = "parcial"
    CANCELADA  = "cancelada"
    PENDIENTE  = "pendiente"
