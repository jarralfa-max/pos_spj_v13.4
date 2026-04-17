
# core/services/hardware_service.py
import logging
import json
try:
    import serial
except ImportError:
    serial = None  # pyserial opcional — hardware físico no disponible
from typing import Dict, Any

logger = logging.getLogger(__name__)

class HardwareService:
    """
    Capa de Abstracción de Hardware (HAL).
    Centraliza la comunicación con puertos COM, USB y Red.
    """
    def __init__(self, db_conn):
        self.db = db_conn
        self._cache_config = {}
        self.load_configs()

    def load_configs(self):
        """Carga todas las configuraciones activas a la memoria RAM."""
        try:
            rows = self.db.execute("SELECT tipo, configuraciones FROM hardware_config WHERE activo = 1").fetchall()
            for row in rows:
                self._cache_config[row['tipo']] = json.loads(row['configuraciones']) if row['configuraciones'] else {}
            logger.info("Configuraciones de hardware cargadas en memoria.")
        except Exception as e:
            logger.error("Error cargando hardware_config: %s", e)

    @staticmethod
    def _safe_baud(config: Dict[str, Any], default: int = 9600) -> int:
        """
        Normaliza baud rate desde claves legacy (`baud`) o nuevas (`baud_rate`).
        Retorna default si el valor es inválido.
        """
        raw = config.get("baud_rate", config.get("baud", default))
        try:
            baud = int(raw)
            if 1200 <= baud <= 115200:
                return baud
        except Exception:
            pass
        return default

    # --- 1. CAJÓN DE DINERO ---
    def open_cash_drawer(self) -> bool:
        """Abre el cajón enviando el pulso a la impresora o puerto directo."""
        config = self._cache_config.get('cajon', {})
        if not config: return False
        
        metodo = config.get('metodo', 'escpos') # 'escpos' o 'serial'
        
        try:
            if metodo == 'escpos':
                # El pulso Kick-Out via ESC/POS
                pulse = bytes([0x1B, 0x70, 0x00, 0x32, 0xFA])
                # Aquí llamarías a la instancia de tu impresora para mandar el byte
                return self._send_raw_to_printer(pulse)
            elif metodo == 'serial':
                if serial is None:
                    return False
                puerto = config.get("puerto")
                if not puerto:
                    return False
                baud = self._safe_baud(config)
                with serial.Serial(puerto, baud, timeout=1) as s:
                    s.write(bytes([0x10, 0x14, 0x01, 0x00, 0x05]))
            return True
        except Exception as e:
            logger.error("Fallo al abrir cajón: %s", e)
            return False

    # --- 2. BÁSCULA DIGITAL ---
    def read_scale(self) -> float:
        """Lee el puerto serial de la báscula y extrae el peso."""
        config = self._cache_config.get('bascula', {})
        if not config:
            return 0.0
        if config.get("activo", True) is False:
            logger.info("Báscula desactivada por configuración.")
            return 0.0
        if serial is None:
            logger.warning("pyserial no disponible — báscula deshabilitada")
            return 0.0
        puerto = config.get("puerto")
        if not puerto:
            return 0.0

        try:
            baud = self._safe_baud(config)
            with serial.Serial(puerto, baud, timeout=0.5) as bascula:
                comando = config.get('comando_lectura', 'P\r\n').encode('utf-8')
                bascula.write(comando)
                respuesta = bascula.readline().decode('utf-8', errors='ignore').strip()
                
                # Usar lógica de parseo según fabricante (Rhino, Torrey, CAS)
                return self._parse_scale_response(respuesta)
        except Exception as e:
            logger.warning(f"Error leyendo báscula en {config.get('puerto')}: {e}")
            return 0.0

    def get_weight(self, manual_weight: float = 0.0) -> float:
        """
        API unificada para POS:
        1) intenta lectura de báscula
        2) si no hay lectura válida, retorna peso manual saneado.
        """
        w = self.read_scale()
        if w > 0:
            return w
        try:
            mw = float(manual_weight or 0.0)
            return max(0.0, mw)
        except Exception:
            return 0.0

    def _parse_scale_response(self, raw_data: str) -> float:
        """Extrae el float de la cadena que devuelve la báscula."""
        import re
        match = re.search(r'([+-]?\d+\.\d+)', raw_data)
        if match: return abs(float(match.group(1)))
        return 0.0

    # --- 3. IMPRESORAS (Tickets y Etiquetas) ---
    def print_kitchen_ticket(self, items: list, folio: str = "") -> bool:
        """
        Imprime ticket de cocina/preparación en la impresora trasera.
        Usa el puerto configurado como 'impresora_cocina_puerto'.
        """
        try:
            row = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave='impresora_cocina_puerto'"
            ).fetchone()
            puerto = row[0] if row else None
            if not puerto:
                return False  # Sin impresora de cocina configurada

            ESC = b'\x1b'
            INIT   = ESC + b'@'
            BOLD_ON  = ESC + b'E\x01'
            BOLD_OFF = ESC + b'E\x00'
            CUT    = b'\x1d\x56\x42\x00'

            lines = [INIT, BOLD_ON, b'-- TICKET COCINA --\n', BOLD_OFF]
            if folio:
                lines.append(f"Folio: {folio}\n".encode('cp850','replace'))
            import datetime
            lines.append(f"Hora: {datetime.datetime.now().strftime('%H:%M:%S')}\n".encode())
            lines.append(b'-' * 28 + b'\n')
            for item in items:
                nombre   = str(item.get('nombre',''))[:22]
                cantidad = float(item.get('cantidad', 1))
                lines.append(f"{cantidad:.1f}x {nombre}\n".encode('cp850','replace'))
            lines.append(b'\n\n')
            lines.append(CUT)

            payload = b''.join(lines)
            return self._send_raw_to_printer_port(payload, puerto)
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("print_kitchen_ticket: %s", e)
            return False

    def _send_raw_to_printer_port(self, data: bytes, puerto: str) -> bool:
        """Envía bytes raw a un puerto específico."""
        try:
            if puerto.startswith('/dev/') or puerto.upper().startswith('COM'):
                if serial is None:
                    return False
                import serial as _serial
                with _serial.Serial(puerto, 9600, timeout=2) as s:
                    s.write(data)
            else:
                with open(puerto, 'wb') as f:
                    f.write(data)
            return True
        except Exception:
            return False

    def _send_raw_to_printer(self, data: bytes) -> bool:
        config = self._cache_config.get('impresora_ticket', {})
        tipo_conexion = config.get('conexion', 'USB')
        
        try:
            if tipo_conexion == 'USB':
                from escpos.printer import Usb
                p = Usb(config['vid'], config['pid'])
                p._raw(data)
                p.close()
            elif tipo_conexion == 'Red':
                from escpos.printer import Network
                p = Network(config['ip'])
                p._raw(data)
                p.close()
            return True
        except Exception as e:
            logger.error("Error de impresora: %s", e)
            return False

    # (Aquí puedes agregar métodos para testear conexiones que llamará la UI)
