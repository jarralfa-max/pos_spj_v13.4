"""Suppliers bounded context — the single supplier master (domain layer).

Pure business logic: entities, value objects, policies and events. No SQL, no
frameworks, no UI. Identity is UUIDv7 (backend.shared.ids.new_uuid); the human
supplier_code never replaces it.
"""
