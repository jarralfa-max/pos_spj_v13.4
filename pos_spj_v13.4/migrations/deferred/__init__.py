"""Deferred migrations — NOT registered in migrations/engine.py.

These run ONLY when invoked explicitly (manual cutover step), never as part of the
automatic migration sequence. See legacy_inventory_drop.py.
"""
