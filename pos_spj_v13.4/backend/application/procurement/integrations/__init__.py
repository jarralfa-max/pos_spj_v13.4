"""PUR-11 — procurement integrations.

Wires the procurement bounded context to the rest of the ERP through events:
- inbound: POS / forecast / minimum-stock replenishment needs → requisitions;
- outbound: receipts → inventory; payables → CxP; immediate payments →
  treasury/petty-cash; receipts → supplier performance.

The procurement context stays decoupled: it publishes canonical events and never
imports the downstream services directly.
"""
