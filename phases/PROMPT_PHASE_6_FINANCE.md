Decouple finance into event-driven system.

---

# 🧠 TESTS

- test_finance_service_methods.py
- test_fase3_plan_cuentas.py
- test_fase3_capital_account.py

---

# 🎯 GOAL

Finance reacts to events only

---

# 🧩 TASK

Remove:
- direct finance mutations

Add:
- handlers for:
  - SALE_CREATED
  - PURCHASE_CREATED