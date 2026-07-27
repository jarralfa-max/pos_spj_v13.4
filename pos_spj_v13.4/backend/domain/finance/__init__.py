"""Finance bounded context — pure domain layer.

No framework, UI, or infrastructure dependencies are allowed in this package.
All identities are UUIDv7 strings produced by ``backend.shared.ids.new_uuid``.
All monetary amounts are ``Money`` value objects backed by ``Decimal``.
"""
