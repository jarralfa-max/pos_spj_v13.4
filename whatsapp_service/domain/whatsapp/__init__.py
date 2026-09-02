# domain/whatsapp — Dominio puro del canal WhatsApp (WA-2)
#
# Sin dependencias de FastAPI, SQLite, httpx ni ningún otro detalle de
# infraestructura (regla 4 del skill de refactor). La única excepción
# deliberada es `_ids.py`, que envuelve el generador UUIDv7 canónico del
# repo (REGLA CERO, no negociable a nivel de todo el proyecto).
