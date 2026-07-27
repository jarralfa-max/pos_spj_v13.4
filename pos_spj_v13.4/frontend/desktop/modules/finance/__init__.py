"""Finance desktop module — presentation only.

Rules: no SQL, no repositories, no db connections, no business rules, no
commit/rollback, no account decisions. Reads go through QueryServices and
mutations through UseCases, both wired by ``finance_routes`` outside the view.
"""
