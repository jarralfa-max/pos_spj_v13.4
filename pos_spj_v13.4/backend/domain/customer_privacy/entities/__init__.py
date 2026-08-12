"""Entities for the Customer Privacy bounded context (CRM-9).

``CustomerConsent`` records are append-only evidence, never overwritten in
place — capturing consent again for the same (customer, type) pair creates
a NEW row superseding the previous one, so the full consent history stays
auditable (§44's "evidencia de consentimiento" is itself a protected field
per §75). ``CustomerCommunicationPreference`` is the one exception: it is a
1:1 settings record per customer (like CRM-8's CustomerCreditProfile), not
an append-only log.
"""
