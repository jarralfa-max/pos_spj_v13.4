# config/numbers.py — Routing por número de WhatsApp
"""
Cada número de WhatsApp tiene un tipo que determina el flujo.
Se configura en la BD del ERP (tabla wa_numeros).
"""
from __future__ import annotations
from enum import Enum
from typing import Optional, Dict, List
import logging

logger = logging.getLogger("wa.numbers")


class NumeroTipo(str, Enum):
    VENTAS = "ventas"           # Atención a clientes, pedidos, cotizaciones
    INTERNO = "interno"         # Staff: alertas, RRHH, comunicación interna
    NOTIFICACIONES = "notif"    # Solo salida: notificaciones automáticas
    GLOBAL = "global"           # Todas las sucursales — requiere selección


class NumeroConfig:
    """Configuración de un número de WhatsApp."""

    def __init__(self, phone_number_id: str, tipo: NumeroTipo,
                 sucursal_id: Optional[int] = None,
                 sucursal_nombre: str = "", display_name: str = ""):
        self.phone_number_id = phone_number_id
        self.tipo = tipo
        self.sucursal_id = sucursal_id
        self.sucursal_nombre = sucursal_nombre
        self.display_name = display_name

    @property
    def es_global(self) -> bool:
        return self.tipo == NumeroTipo.GLOBAL

    @property
    def requiere_sucursal(self) -> bool:
        return self.es_global or self.sucursal_id is None


class NumberRegistry:
    """Registro de números de WhatsApp configurados."""

    def __init__(self, db_conn=None):
        self._numbers: Dict[str, NumeroConfig] = {}
        if db_conn:
            self._load_from_db(db_conn)

    def _load_from_db(self, db):
        """Carga configuración desde tabla REAL del ERP."""
        try:
            rows = db.execute("""
                SELECT 
                    meta_phone_id,
                    canal,
                    sucursal_id,
                    nombre_sucursal,
                    numero_negocio
                FROM whatsapp_numeros
                WHERE activo = 1
            """).fetchall()

            for r in rows:
                phone_id = r[0]
                canal = r[1] or "ventas"

                # Mapear canal → tipo
                if canal == "todos":
                    tipo = NumeroTipo.GLOBAL
                elif canal == "clientes":
                    tipo = NumeroTipo.VENTAS
                elif canal == "rrhh":
                    tipo = NumeroTipo.INTERNO
                else:
                    tipo = NumeroTipo.VENTAS

                cfg = NumeroConfig(
                    phone_number_id=phone_id,
                    tipo=tipo,
                    sucursal_id=r[2],
                    sucursal_nombre=r[3] or "",
                    display_name=r[4] or "",
                )

                self._numbers[phone_id] = cfg

                logger.info(
                    "Número ERP: %s (%s) → sucursal %s",
                    phone_id, tipo, r[3] or "global"
                )

        except Exception as e:
            logger.error("Error cargando números WA desde ERP: %s", e)

    def get(self, phone_number_id: str) -> Optional[NumeroConfig]:
        return self._numbers.get(phone_number_id)

    def get_by_tipo(self, tipo: NumeroTipo) -> List[NumeroConfig]:
        return [n for n in self._numbers.values() if n.tipo == tipo]

    def get_for_sucursal(self, sucursal_id: int) -> Optional[NumeroConfig]:
        for n in self._numbers.values():
            if n.sucursal_id == sucursal_id and n.tipo == NumeroTipo.VENTAS:
                return n
        return None
