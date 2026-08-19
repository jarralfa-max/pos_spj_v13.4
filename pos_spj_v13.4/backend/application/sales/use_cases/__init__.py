"""Sales/POS application use cases (SALES-6/POS-6).

No standalone `Command` dataclasses — `execute()` takes explicit keyword
arguments directly. This mirrors this repo's newer, ACTIVE convention
(backend/application/cash_register/shift_use_cases.py,
backend/application/customers/use_cases/lifecycle_use_cases.py), confirmed
via research to be the pattern actively replacing the older generic
`backend/application/commands/*Command` + `backend/application/use_cases/`
layer (see tests/architecture/allowlists.py's own entry marking
`customer_commands.py` as legacy-to-retire). The master prompt's "Commands"
bullet (§67 POS-6) is satisfied by these typed `execute()` signatures, not a
separate Command object — same reconciliation this pipeline has made in
every prior phase when the master prompt's abstract structure diverged from
this repo's real, established convention.
"""
