"""Slaughter preparation (§37/§50, PROC-24) — future flow scaffolding.

Not implemented, not enabled (see `feature_flag.SLAUGHTER_ENABLED`). Mirrors
`backend/domain/inventory/slaughter/` (INV-21), which stubs the *inventory*
side of this same future capability: livestock/carcass/output lots and the
stock movements a real slaughter module would post. This package stubs the
*operational* side that Procesamiento Cárnico itself would own — animal
reception, ante/post-mortem inspection, carcass classification, condemnation,
chilling — matching the 12 `SLAUGHTER_*` permissions already defined
(PROC-1) and the `*_FUTURE` values already in `ProcessType` (PROC-2).
"""
