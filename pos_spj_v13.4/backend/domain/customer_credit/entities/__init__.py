"""Entities for the Customer Credit bounded context (CRM-8).

``CustomerCreditProfile`` is the only entity — §37-40 doesn't name a
separate evidence/history entity for review or approval the way Leads
(LeadQualification) or Service Cases (ServiceCaseResolution/
ServiceCaseEscalation) have one; the profile's own fields
(``authorized_at``/``authorized_by_user_id``, ``review_at``) already carry
that evidence, and each mutation is separately audited via
``CustomerCreditAuditRepository`` — adding a parallel entity for what the
audit log already records would be redundant, not extra rigor.

``current_exposure``/``available_credit`` (also named in §37-40) are
deliberately NOT columns on this entity — see this module's
``customer_credit_profile.py`` docstring for why.
"""
