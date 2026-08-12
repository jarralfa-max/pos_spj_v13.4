"""Entities for the CRM (relationship) bounded context (CRM-4+).

``Lead`` is CRM-4's aggregate root — owns its own status transitions
(mirrors backend/domain/customers/entities/customer.py::Customer).
``LeadQualification`` is the evidence record a qualification decision
leaves behind (§17: "La calificación debe dejar evidencia").
"""
