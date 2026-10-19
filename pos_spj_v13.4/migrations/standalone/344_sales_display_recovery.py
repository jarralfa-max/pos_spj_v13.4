"""Governed POS display preferences. No new business tables or operational writes."""
from backend.application.settings.catalog import sync_configuration_catalog
import json


def run(conn):
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='configuration_definitions'").fetchone()
    if exists:
        sync_configuration_catalog(conn)
    layouts = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='display_layouts'").fetchone()
    if layouts:
        for layout_id, raw in conn.execute("SELECT id, sections_json FROM display_layouts").fetchall():
            sections = json.loads(raw or "[]")
            codes = {section["code"] for section in sections}
            order = max((section["order"] for section in sections), default=-1) + 1
            for code in ("TAX", "POINTS", "SCALE", "PAYMENT", "BRANDING"):
                if code not in codes:
                    sections.append({"code": code, "order": order, "enabled": True})
                    order += 1
            conn.execute("UPDATE display_layouts SET sections_json=? WHERE id=?",
                         (json.dumps(sections), layout_id))
    conn.commit()


up = run
