"""Read the selected WhatsApp integration; never guess across branches.

An existing instance is authoritative, including missing/revoked credentials.
Legacy settings are readable only when no WhatsApp instance exists.
"""
from __future__ import annotations

import json


ALIASES = {
    "meta_token": ("wa_meta_token", "wa_access_token", "meta_token", "access_token"),
    "meta_phone_id": ("wa_meta_phone_id", "wa_phone_number_id", "meta_phone_id", "phone_number_id"),
    "verify_token": ("wa_verify_token", "verify_token"),
    "app_secret": ("wa_app_secret", "app_secret"),
    "internal_api_key": ("wa_internal_api_key", "internal_api_key"),
    "base_url": ("wa_base_url", "wa_microservicio_url", "base_url", "microservicio_url"),
}


def read_whatsapp_setting(connection, key: str, secret_gateway, *, instance_id: str = "") -> str | None:
    """None permits bootstrap fallback; empty means an authoritative missing value."""
    key = key.removeprefix("wa_")
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    rows = []
    if {"integration_definitions", "integration_instances"} <= tables:
        rows = connection.execute(
            "SELECT i.id, i.config_json, i.credential_references_json, i.active, d.active "
            "FROM integration_instances i JOIN integration_definitions d ON d.id=i.definition_id "
            "WHERE d.code='WHATSAPP'" + (" AND i.id=?" if instance_id else ""),
            (instance_id,) if instance_id else (),
        ).fetchall()
    if instance_id and not rows:
        raise RuntimeError("WhatsApp instance does not exist in the configured database")
    if not instance_id:
        active = [r for r in rows if r[3] and r[4]]
        if len(active) > 1:
            raise RuntimeError("Multiple WhatsApp instances: configure WA_INTEGRATION_INSTANCE_ID")
        rows = active or rows[:1]
    if rows:
        row = rows[0]
        if not row[3] or not row[4]:
            return ""
        config, references = json.loads(row[1] or "{}"), json.loads(row[2] or "{}")
        aliases = ALIASES.get(key, ("wa_" + key, key))
        for name in aliases:
            if name in references:
                reference = secret_gateway.describe(references[name])
                if reference is None or reference.status == "REVOKED":
                    return ""
                return secret_gateway.get_secret(references[name]) or ""
        if key in {"meta_phone_id", "base_url"}:
            return next((str(config[n]) for n in aliases if config.get(n)), "")
        return ""
    if "configuraciones" in tables:
        row = connection.execute("SELECT valor FROM configuraciones WHERE clave=?", ("wa_" + key,)).fetchone()
        if row and row[0]:
            return str(row[0])
    return None
