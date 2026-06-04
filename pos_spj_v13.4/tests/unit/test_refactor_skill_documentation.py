from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "pos_spj_v13.4" / "docs" / "skills" / "SPJ_REFACTOR_SKILL.md"


def test_refactor_skill_defines_mandatory_phase_guardrails() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")

    required_rules = [
        "No modificar lógica de negocio funcional sin pruebas de protección.",
        "PyQt no debe ejecutar SQL.",
        "PyQt no debe hacer `commit()` ni `rollback()`.",
        "Solo `migrations/` puede modificar schema.",
        "Toda operación crítica debe pasar por Use Case / Application Service.",
        "Toda lectura para UI debe pasar por QueryService.",
    ]

    missing_rules = [rule for rule in required_rules if rule not in content]
    assert not missing_rules, "Missing mandatory refactor rules: " + ", ".join(missing_rules)
