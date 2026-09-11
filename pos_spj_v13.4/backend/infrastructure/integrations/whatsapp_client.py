"""Cliente REST del ERP hacia el microservicio de WhatsApp.

Reemplaza `core/integrations/whatsapp_client.py`, borrado con la carpeta
`core/`. No se recuperó del historial (§18): el contrato se leyó del propio
microservicio, que sigue en el repositorio (`whatsapp_service/`) y es la única
autoridad sobre lo que acepta.

LO QUE CAMBIÓ RESPECTO AL CLIENTE ANTERIOR, y no es un detalle
--------------------------------------------------------------
El cliente viejo se autenticaba con una cabecera `X-Internal-Key` de texto
plano. Esa forma YA NO EXISTE: WA-1 la sustituyó por firma HMAC porque la
comparación anterior no era de tiempo constante y, peor, fallaba ABIERTA si la
clave no estaba configurada (`whatsapp_security_audit.md`, S1/S2/S3).

Reconstruir el cliente "como estaba" habría producido algo que el microservicio
rechaza con 401 en cada llamada. El secreto compartido es el mismo; lo que
cambió es que ahora se usa como clave HMAC, no como valor comparado.

FORMATO DE LA FIRMA — tiene que coincidir byte a byte con
`whatsapp_service/middleware/service_auth.py::sign_request`:

    body_hash     = sha256(cuerpo).hexdigest()
    cadena        = f"{service_id}:{timestamp}:{nonce}:{body_hash}"
    firma         = HMAC-SHA256(cadena, secreto).hexdigest()

Se mantiene una copia corta de esa lógica aquí en vez de importarla: el
microservicio es un paquete de nivel superior distinto y desplegable por
separado, así que no hay un módulo común que ambos puedan importar sin
acoplarlos.

NUNCA LANZA. Un fallo de WhatsApp —servicio caído, teléfono inválido, red— no
puede tumbar la operación de negocio que lo disparó. Todos los métodos
devuelven `True`/`False` según si el microservicio confirmó el envío.

CONFIGURACIÓN
-------------
Los secretos viven en `configuraciones` bajo el prefijo `wa_`, con respaldo en
variables de entorno — el mismo esquema que usa el microservicio para leerlos.

`wa_base_url` es una elección de este archivo: la clave que usaba el cliente
anterior se fue con él y no quedó rastro de su nombre. El valor por omisión
(`http://127.0.0.1:8000`) es el puerto que el propio `whatsapp_service/main.py`
documenta en sus instrucciones de arranque. Una instalación que tuviera la URL
guardada bajo otro nombre hay que reconfigurarla.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.request

logger = logging.getLogger("spj.integrations.whatsapp")

#: Identidad con la que el ERP se presenta. Debe coincidir con
#: `ERP_CORE_SERVICE` en el middleware del microservicio.
ERP_SERVICE_ID = "erp-core"

#: El microservicio rechaza timestamps con más de 120 s de desviación; un
#: tiempo de espera mayor que eso haría que un reintento lento llegara ya
#: caducado y sin explicación visible.
DEFAULT_TIMEOUT_SECONDS = 10

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def sign_request(service_id: str, timestamp: str, nonce: str, body: bytes, secret: str) -> str:
    """HMAC-SHA256 sobre `service_id:timestamp:nonce:sha256(cuerpo)`.

    El cuerpo se resume una sola vez y su digest entra en la cadena firmada,
    en lugar de firmar el cuerpo completo. Copia exacta de la del
    microservicio: cualquier divergencia, por mínima que sea, se manifiesta
    como un 401 sin más detalle.
    """
    body_hash = hashlib.sha256(body or b"").hexdigest()
    signed = f"{service_id}:{timestamp}:{nonce}:{body_hash}"
    return hmac.new(secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256).hexdigest()


class WhatsAppClient:
    def __init__(
        self, *, connection=None, base_url: str = "", internal_key: str = "",
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._connection = connection
        self._base_url = (base_url or self._setting("base_url", "WA_BASE_URL")
                          or DEFAULT_BASE_URL).rstrip("/")
        self._secret = internal_key or self._setting(
            "internal_api_key", "WA_INTERNAL_API_KEY", "INTERNAL_API_KEY")
        self._timeout = timeout

    # ── configuración ────────────────────────────────────────────────────
    def _setting(self, key: str, *env_names: str) -> str:
        """`configuraciones.wa_<key>`, con respaldo en variables de entorno.

        La base de datos manda sobre el entorno a propósito: es lo que el
        usuario configura desde la pantalla de Integraciones, y sería
        desconcertante que un `.env` olvidado en la máquina lo anulara.
        """
        if self._connection is not None:
            try:
                row = self._connection.execute(
                    "SELECT valor FROM configuraciones WHERE clave=? LIMIT 1",
                    (f"wa_{key}",)).fetchone()
                if row and str(row[0] or "").strip():
                    return str(row[0]).strip()
            except Exception as exc:
                logger.debug("No se pudo leer wa_%s de la base: %s", key, exc)
        for name in env_names:
            value = os.getenv(name, "").strip()
            if value:
                return value
        return ""

    # ── transporte ───────────────────────────────────────────────────────
    def _post(self, path: str, payload: dict) -> bool:
        """POST firmado. Devuelve si el microservicio confirmó el envío.

        Sin secreto configurado se rechaza ANTES de salir a la red: firmar con
        una clave vacía produce una firma válida en forma pero que el servicio
        rechaza, y el síntoma sería un 401 confuso en vez de "falta configurar
        la integración".
        """
        if not self._secret:
            logger.warning(
                "WhatsApp sin clave interna configurada (wa_internal_api_key); "
                "no se envía %s", path)
            return False

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        request = urllib.request.Request(
            f"{self._base_url}{path}", data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Service-Id": ERP_SERVICE_ID,
                "X-Timestamp": timestamp,
                "X-Nonce": nonce,
                "X-Signature": sign_request(
                    ERP_SERVICE_ID, timestamp, nonce, body, self._secret),
                # No participa en la firma; sólo sirve para correlacionar
                # ambos lados en los registros.
                "X-Correlation-Id": secrets.token_hex(8),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                data = json.loads(response.read().decode("utf-8") or "{}")
            return bool(data.get("ok"))
        except urllib.error.HTTPError as exc:
            logger.warning("WhatsApp %s respondió %s", path, exc.code)
            return False
        except Exception as exc:
            # Incluye servicio caído, DNS, timeout y respuesta no-JSON. Todos
            # significan lo mismo para quien llama: no se notificó.
            logger.warning("WhatsApp %s no disponible: %s", path, exc)
            return False

    # ── operaciones ──────────────────────────────────────────────────────
    def notificar_pedido_listo(self, phone: str, folio: str, sucursal: str = "") -> bool:
        """Plantilla dedicada del microservicio, no un mensaje genérico."""
        return self._post("/api/notify/pedido-listo",
                          {"phone": phone, "folio": folio, "sucursal": sucursal or ""})

    def enviar_mensaje(self, phone: str, message: str) -> bool:
        return self._post("/api/notify/send", {"phone": phone, "message": message})
