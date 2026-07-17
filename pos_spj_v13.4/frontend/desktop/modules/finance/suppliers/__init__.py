"""Suppliers UI — a page inside Finanzas (no standalone menu).

The single supplier master, reachable from Finanzas and (contextually) from
Compras. UI only: it delegates to the SupplierPresenter, which uses supplier
query services (reads) and use cases (mutations). No SQL, no repositories, no
colors here.
"""
