# core/services/qr_parser_service.py — SPJ POS v13.30 — FASE 1.5
"""
QRParserService — Parsea códigos QR/barcodes escaneados.

PROBLEMA:
    Cuando se escanea un QR de cliente, el código crudo se pone en
    el campo de nombre. Ej: "CLT-42-Juan Pérez" → nombre="CLT-42-Juan Pérez"
    
SOLUCIÓN:
    Parsea el QR, extrae client_id y nombre por separado.
    Soporta múltiples formatos de QR.

FORMATOS SOPORTADOS:
    1. ID numérico:          "42"         → client_id=42
    2. Prefijo CLT:          "CLT-42"     → client_id=42
    3. Prefijo + nombre:     "CLT-42-Juan Pérez" → client_id=42, nombre="Juan Pérez"
    4. Código tarjeta:       "TF-A1B2C3"  → tipo=tarjeta, codigo="TF-A1B2C3"
    5. UUID contenedor:      "abc123def456" (hex 12+) → tipo=contenedor
    6. Teléfono:             "4421234567"  → tipo=telefono
    7. Código de barras prod: "7501234567890" → tipo=producto (EAN-13)
    8. Texto libre:          "Juan Pérez"  → tipo=busqueda
"""
from __future__ import annotations
import re
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("spj.qr")


class QRType:
    CLIENT_ID = "client_id"
    TARJETA = "tarjeta"
    CONTENEDOR = "contenedor"
    TELEFONO = "telefono"
    PRODUCTO = "producto"
    BUSQUEDA = "busqueda"


@dataclass
class QRResult:
    """Resultado de parsear un código QR/barcode."""
    tipo: str                          # QRType.*
    raw: str = ""                      # Código crudo escaneado
    client_id: Optional[int] = None
    nombre: str = ""
    codigo: str = ""                   # Código de tarjeta/producto
    valid: bool = True
    error: str = ""

    def to_dict(self) -> Dict:
        return {
            "tipo": self.tipo, "raw": self.raw,
            "client_id": self.client_id, "nombre": self.nombre,
            "codigo": self.codigo, "valid": self.valid, "error": self.error,
        }


# Patrones de QR
_RE_CLT_ID_NAME = re.compile(r'^CLT-(\d+)-(.+)$', re.IGNORECASE)
_RE_CLT_ID = re.compile(r'^CLT-(\d+)$', re.IGNORECASE)
_RE_TARJETA = re.compile(r'^(TF|TAR|CARD)-([A-Za-z0-9]+)$', re.IGNORECASE)
_RE_NUMERIC_ID = re.compile(r'^\d{1,6}$')
_RE_TELEFONO = re.compile(r'^\d{10}$')
_RE_UUID_HEX = re.compile(r'^[a-f0-9]{12,}$', re.IGNORECASE)
_RE_EAN = re.compile(r'^\d{8}(\d{5})?$')  # EAN-8 o EAN-13


class QRParserService:
    """Parsea códigos QR escaneados y separa client_id de nombre."""

    def __init__(self, db_conn=None):
        self.db = db_conn

    def parse(self, raw_code: str) -> QRResult:
        """
        Parsea un código QR/barcode escaneado.
        Retorna QRResult con tipo, client_id, nombre separados.
        """
        code = raw_code.strip()
        if not code:
            return QRResult(tipo=QRType.BUSQUEDA, raw=code,
                            valid=False, error="Código vacío")

        # 1. Formato CLT-{id}-{nombre}
        m = _RE_CLT_ID_NAME.match(code)
        if m:
            cid = int(m.group(1))
            nombre = m.group(2).strip()
            logger.debug("QR parse: CLT-%d-%s", cid, nombre)
            return QRResult(
                tipo=QRType.CLIENT_ID, raw=code,
                client_id=cid, nombre=nombre, codigo=code)

        # 2. Formato CLT-{id}
        m = _RE_CLT_ID.match(code)
        if m:
            cid = int(m.group(1))
            nombre = self._lookup_client_name(cid)
            return QRResult(
                tipo=QRType.CLIENT_ID, raw=code,
                client_id=cid, nombre=nombre, codigo=code)

        # 3. Tarjeta de fidelidad (TF-XXXX)
        m = _RE_TARJETA.match(code)
        if m:
            return QRResult(
                tipo=QRType.TARJETA, raw=code,
                codigo=code)

        # 4. Teléfono (10 dígitos)
        if _RE_TELEFONO.match(code):
            return QRResult(
                tipo=QRType.TELEFONO, raw=code,
                codigo=code)

        # 5. ID numérico puro (1-6 dígitos, no teléfono)
        if _RE_NUMERIC_ID.match(code):
            cid = int(code)
            nombre = self._lookup_client_name(cid)
            return QRResult(
                tipo=QRType.CLIENT_ID, raw=code,
                client_id=cid, nombre=nombre, codigo=code)

        # 6. UUID contenedor (hex largo)
        if _RE_UUID_HEX.match(code):
            return QRResult(
                tipo=QRType.CONTENEDOR, raw=code,
                codigo=code)

        # 7. EAN-8 / EAN-13 (código de barras producto)
        if _RE_EAN.match(code):
            return QRResult(
                tipo=QRType.PRODUCTO, raw=code,
                codigo=code)

        # 8. Cualquier otra cosa → búsqueda de texto
        return QRResult(
            tipo=QRType.BUSQUEDA, raw=code,
            nombre=code, codigo=code)

    def parse_client_qr(self, raw_code: str) -> QRResult:
        """
        Parsea específicamente para contexto cliente.
        Si el QR tiene formato CLT-{id}-{nombre}, separa los campos.
        Si no, busca en BD por código/teléfono.
        """
        result = self.parse(raw_code)

        # Si ya se resolvió como client_id, retornar
        if result.tipo == QRType.CLIENT_ID and result.client_id:
            return result

        # Si es tarjeta, buscar en BD
        if result.tipo == QRType.TARJETA and self.db:
            return self._lookup_tarjeta(raw_code.strip())

        # Si es teléfono, buscar cliente por teléfono
        if result.tipo == QRType.TELEFONO and self.db:
            return self._lookup_by_phone(raw_code.strip())

        # Fallback: buscar por cualquier campo
        if self.db:
            return self._lookup_flexible(raw_code.strip())

        return result

    # ── Lookups en BD ─────────────────────────────────────────────────────────

    def _lookup_client_name(self, client_id: int) -> str:
        """Busca el nombre del cliente por ID."""
        if not self.db:
            return ""
        try:
            row = self.db.execute(
                "SELECT nombre FROM clientes WHERE id=?",
                (client_id,)).fetchone()
            return row[0] if row else ""
        except Exception:
            return ""

    def _lookup_tarjeta(self, codigo: str) -> QRResult:
        """Busca tarjeta de fidelidad y retorna datos del cliente."""
        try:
            row = self.db.execute(
                "SELECT t.codigo, c.id, c.nombre, c.telefono, "
                "COALESCE(c.puntos,0) "
                "FROM tarjetas_fidelidad t "
                "JOIN clientes c ON c.id=t.id_cliente "
                "WHERE t.codigo=? AND t.activa=1 LIMIT 1",
                (codigo,)).fetchone()
            if row:
                return QRResult(
                    tipo=QRType.TARJETA, raw=codigo,
                    client_id=row[1], nombre=row[2],
                    codigo=row[0])
        except Exception:
            pass
        return QRResult(tipo=QRType.TARJETA, raw=codigo,
                        valid=False, error="Tarjeta no encontrada")

    def _lookup_by_phone(self, telefono: str) -> QRResult:
        try:
            row = self.db.execute(
                "SELECT id, nombre FROM clientes "
                "WHERE telefono=? AND activo=1 LIMIT 1",
                (telefono,)).fetchone()
            if row:
                return QRResult(
                    tipo=QRType.CLIENT_ID, raw=telefono,
                    client_id=row[0], nombre=row[1], codigo=telefono)
        except Exception:
            pass
        return QRResult(tipo=QRType.TELEFONO, raw=telefono,
                        valid=False, error="Teléfono no registrado")

    def _lookup_flexible(self, codigo: str) -> QRResult:
        """Búsqueda flexible: ID, teléfono, código QR, tarjeta."""
        try:
            row = self.db.execute(
                "SELECT id, nombre FROM clientes "
                "WHERE CAST(id AS TEXT)=? OR telefono=? OR codigo_qr=? "
                "LIMIT 1",
                (codigo, codigo, codigo)).fetchone()
            if row:
                return QRResult(
                    tipo=QRType.CLIENT_ID, raw=codigo,
                    client_id=row[0], nombre=row[1], codigo=codigo)
        except Exception:
            pass
        return QRResult(tipo=QRType.BUSQUEDA, raw=codigo,
                        nombre=codigo, valid=False,
                        error="No encontrado")
