
# utils/helpers.py — SPJ POS v12
"""
Funciones de utilidad compartidas por todos los módulos del POS.
Agrupa helpers de formato, validación, fechas, texto y red.
"""
from __future__ import annotations
import re, os, uuid, hashlib, json
from datetime import datetime, date
from typing import Any


# ═══════════════════════════════════════════════════════════════
# FORMATO NUMÉRICO
# ═══════════════════════════════════════════════════════════════

def formato_moneda(valor, simbolo: str = "$") -> str:
    """$1,234.56"""
    try:
        return f"{simbolo}{float(valor):,.2f}"
    except (TypeError, ValueError):
        return f"{simbolo}0.00"


def formato_kg(valor) -> str:
    """1.250 kg"""
    try:
        return f"{float(valor):.3f} kg"
    except (TypeError, ValueError):
        return "0.000 kg"


def safe_float(valor, default: float = 0.0) -> float:
    """Convierte a float sin lanzar excepción."""
    try:
        return float(valor)
    except (TypeError, ValueError):
        return default


def safe_int(valor, default: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return default


def redondear_precio(valor) -> float:
    return round(safe_float(valor), 2)


# ═══════════════════════════════════════════════════════════════
# FECHAS Y TIEMPO
# ═══════════════════════════════════════════════════════════════

def fecha_hoy() -> str:
    return date.today().isoformat()       # "2025-03-07"


def fecha_hora_ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fecha_display(valor: str) -> str:
    """ISO → "07/03/2025"  (formato México)."""
    try:
        d = datetime.fromisoformat(str(valor)[:10])
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(valor)[:10]


def fecha_hora_display(valor: str) -> str:
    """ISO datetime → "07/03/2025 14:30"."""
    try:
        d = datetime.fromisoformat(str(valor)[:19])
        return d.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(valor)[:16]


def dias_hasta(fecha_str: str) -> int:
    """Días que faltan para una fecha ISO."""
    try:
        target = date.fromisoformat(str(fecha_str)[:10])
        return (target - date.today()).days
    except Exception:
        return 999


# ═══════════════════════════════════════════════════════════════
# TEXTO Y CADENAS
# ═══════════════════════════════════════════════════════════════

def normalizar_telefono(telefono: str) -> str:
    """
    Normaliza un número de teléfono mexicano.
    Entrada:  "55 1234 5678", "+52 55 1234 5678", "5215512345678"
    Salida:   "5215512345678"  (formato WA)
    """
    digits = re.sub(r"\D", "", str(telefono))
    if digits.startswith("52"):
        digits = digits[2:]
    digits = digits[-10:]  # últimos 10 dígitos
    return "521" + digits if len(digits) == 10 else digits


def capitalizar_nombre(texto: str) -> str:
    """Ana María → Ana María (respeta tildes)."""
    return " ".join(p.capitalize() for p in str(texto).strip().split())


def truncar(texto: str, max_len: int = 30, sufijo: str = "…") -> str:
    texto = str(texto)
    return texto if len(texto) <= max_len else texto[:max_len-len(sufijo)] + sufijo


def slugify(texto: str) -> str:
    """hola mundo → hola_mundo (para nombres de archivo)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(texto))
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[\s-]+", "_", s)


def limpiar_rfc(rfc: str) -> str:
    return re.sub(r"[^A-Z0-9&]", "", str(rfc).upper())


# ═══════════════════════════════════════════════════════════════
# IDs Y CÓDIGOS
# ═══════════════════════════════════════════════════════════════

def generar_folio(prefijo: str = "V", n: int = 1) -> str:
    """V000001, DEL000042, etc."""
    return f"{prefijo}{n:06d}"


def generar_uuid() -> str:
    return str(uuid.uuid4()).replace("-", "").upper()[:20]


def generar_codigo_barras(producto_id: int, sucursal_id: int = 1) -> str:
    """Código EAN-like interno: 7SSSPPPPPP0"""
    return f"7{sucursal_id:03d}{producto_id:06d}0"


# ═══════════════════════════════════════════════════════════════
# VALIDACIÓN
# ═══════════════════════════════════════════════════════════════

def validar_rfc(rfc: str) -> bool:
    patron = r"^[A-ZÑ&]{3,4}\d{6}[A-Z\d]{3}$"
    return bool(re.match(patron, limpiar_rfc(rfc)))


def validar_email(email: str) -> bool:
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", str(email)))


def validar_telefono_mx(tel: str) -> bool:
    digits = re.sub(r"\D", "", tel)
    return len(digits) in (10, 12, 13)


# ═══════════════════════════════════════════════════════════════
# ARCHIVOS Y RUTAS
# ═══════════════════════════════════════════════════════════════

def asegurar_directorio(ruta: str):
    os.makedirs(ruta, exist_ok=True)


def ruta_exportacion(nombre: str, extension: str = "pdf") -> str:
    asegurar_directorio("exports")
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn  = slugify(nombre)
    return f"exports/{fn}_{ts}.{extension}"


def ruta_log(nombre: str) -> str:
    asegurar_directorio("logs")
    return f"logs/{nombre}.log"


# ═══════════════════════════════════════════════════════════════
# RED Y CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════

def get_ip_local() -> str:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def puerto_disponible(puerto: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", puerto)) != 0


# ═══════════════════════════════════════════════════════════════
# BASE DE DATOS
# ═══════════════════════════════════════════════════════════════

def dict_from_row(row) -> dict:
    """sqlite3.Row o tuple → dict seguro."""
    if row is None:
        return {}
    try:
        return dict(row)
    except Exception:
        return {}


def rows_to_dicts(rows) -> list:
    return [dict_from_row(r) for r in rows]


def get_config(conn, clave: str, default: str = "") -> str:
    """Lee configuración de la BD."""
    try:
        row = conn.execute(
            "SELECT valor FROM configuraciones WHERE clave=?", (clave,)).fetchone()
        return row[0] if row else default
    except Exception:
        return default


def set_config(conn, clave: str, valor: str):
    conn.execute(
        "INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES (?,?)",
        (clave, valor))
    try:
        conn.commit()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# JSON SEGURO
# ═══════════════════════════════════════════════════════════════

def json_safe(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def json_parse(texto: str, default=None):
    try:
        return json.loads(texto)
    except Exception:
        return default
