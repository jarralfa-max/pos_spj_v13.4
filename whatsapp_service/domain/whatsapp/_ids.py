# domain/whatsapp/_ids.py — Generador de identidad UUIDv7 (REGLA CERO)
"""
El dominio no debería depender de infraestructura (regla 4 del skill de
refactor), pero REGLA CERO es una excepción explícita y no-negociable a
nivel de todo el repo: `backend/shared/ids.py::new_uuid()` es el ÚNICO
generador de identidad permitido en todo el proyecto, dominio incluido.

Este módulo solo envuelve ese import con el mismo patrón defensivo ya usado
en `whatsapp_service/erp/events.py::_new_event_id()` (WA-1), para que
`domain/whatsapp` también funcione bajo tests sin pasar por `main.py`
(que normalmente ya deja `pos_spj_v13.4/` en `sys.path`).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("wa.domain")


def new_id() -> str:
    """UUIDv7 canónico para cualquier identidad del dominio WhatsApp."""
    try:
        from backend.shared.ids import new_uuid
        return new_uuid()
    except ImportError:
        try:
            import sys
            # whatsapp_service/domain/whatsapp/_ids.py -> ... -> raíz del repo
            erp_path = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            erp_module = os.path.join(erp_path, "pos_spj_v13.4")
            if os.path.exists(erp_module) and erp_module not in sys.path:
                sys.path.insert(0, erp_module)
            from backend.shared.ids import new_uuid
            return new_uuid()
        except ImportError:
            import uuid as _uuid
            logger.warning(
                "backend.shared.ids no importable — usando uuid4 fallback "
                "para identidad de dominio WhatsApp"
            )
            return str(_uuid.uuid4())
