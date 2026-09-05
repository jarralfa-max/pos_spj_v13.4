"""Domain layer for the scenario_planning bounded context (§41-45, BI-19).

A scenario is never saved as a real price/demand/capacity — it's a
counterfactual perturbation applied to inputs, re-run through the same
deterministic pipeline the real forecast/pricing services already use
(§42: "No guardar como precio real").
"""
