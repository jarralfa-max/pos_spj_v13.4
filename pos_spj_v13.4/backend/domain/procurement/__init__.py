"""Procurement bounded context — the single purchasing domain.

Two operative routes over one architecture: direct purchase (fast, secure,
executed inside Compras) and enterprise purchase (requisition → RFQ → order →
receipt → invoice). The POS only detects needs; it never executes purchases.
Pure domain: no SQL, no UI, no frameworks. Money/weight/quantity use Decimal.
"""
