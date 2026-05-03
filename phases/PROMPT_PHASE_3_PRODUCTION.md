Refactor meat production system into event-driven flow.

---

# 🧠 SOURCE OF TRUTH

Tests:
- test_fase0_produccion_historial_compat.py
- test_fase4_stock_validation.py

---

# 🎯 GOAL

Production emits:

PRODUCTION_EXECUTED

---

# 🔍 STEP 1

Locate:
- production_engine.py
- recipe_engine.py
- yield_calculator.py

---

# 🧩 STEP 2

Detect:
- direct inventory manipulation
- cost allocation logic

---

# 🧩 STEP 3 — EVENT

Payload must include:
- raw_materials
- outputs
- yields
- costs

---

# 🧩 STEP 4 — HANDLER

Handler must:
- OUT raw products
- IN derived products

---

# 🧪 STEP 5 — VALIDATION

Ensure:
- yields unchanged
- costs unchanged
- stock consistent