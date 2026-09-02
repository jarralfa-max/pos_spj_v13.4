import pytest

from backend.bootstrap.dependency_graph_validator import DependencyGraphValidator, IssueSeverity
from backend.bootstrap.service_errors import DependencyGraphInvalidError
from backend.bootstrap.service_lifetime import Lifetime
from backend.bootstrap.service_registration import ServiceDependency
from backend.bootstrap.service_registry import ServiceRegistry


@pytest.fixture
def validator() -> DependencyGraphValidator:
    return DependencyGraphValidator()


def test_valid_graph_has_no_issues(validator):
    registry = ServiceRegistry()
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON)
    registry.register("b", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["a"])
    assert validator.validate(registry) == []


def test_missing_required_dependency_is_an_error(validator):
    registry = ServiceRegistry()
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["missing"])
    issues = validator.validate(registry)
    assert len(issues) == 1
    assert issues[0].severity is IssueSeverity.ERROR
    assert issues[0].code == "MISSING_DEPENDENCY"


def test_missing_optional_dependency_is_not_an_error(validator):
    registry = ServiceRegistry()
    registry.register(
        "a", lambda r: object(), lifetime=Lifetime.SINGLETON,
        dependencies=[ServiceDependency(key="missing", optional=True)],
    )
    assert validator.validate(registry) == []


def test_direct_cycle_is_detected(validator):
    registry = ServiceRegistry()
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["b"])
    registry.register("b", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["a"])
    issues = validator.validate(registry)
    cycle_issues = [i for i in issues if i.code == "DEPENDENCY_CYCLE"]
    assert len(cycle_issues) == 1
    assert cycle_issues[0].severity is IssueSeverity.ERROR


def test_indirect_cycle_is_detected(validator):
    registry = ServiceRegistry()
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["b"])
    registry.register("b", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["c"])
    registry.register("c", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["a"])
    issues = validator.validate(registry)
    cycle_issues = [i for i in issues if i.code == "DEPENDENCY_CYCLE"]
    assert len(cycle_issues) == 1


def test_self_dependency_is_a_cycle(validator):
    registry = ServiceRegistry()
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["a"])
    issues = validator.validate(registry)
    assert any(i.code == "DEPENDENCY_CYCLE" for i in issues)


def test_acyclic_diamond_shape_has_no_cycle_issue(validator):
    registry = ServiceRegistry()
    registry.register("root", lambda r: object(), lifetime=Lifetime.SINGLETON)
    registry.register("left", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["root"])
    registry.register("right", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["root"])
    registry.register("top", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["left", "right"])
    assert validator.validate(registry) == []


def test_captive_dependency_singleton_on_session_is_an_error(validator):
    registry = ServiceRegistry()
    registry.register("session_thing", lambda r: object(), lifetime=Lifetime.SESSION)
    registry.register(
        "singleton_thing", lambda r: object(), lifetime=Lifetime.SINGLETON,
        dependencies=["session_thing"],
    )
    issues = validator.validate(registry)
    lifetime_issues = [i for i in issues if i.code == "LIFETIME_INCOMPATIBLE"]
    assert len(lifetime_issues) == 1
    assert lifetime_issues[0].severity is IssueSeverity.ERROR


def test_session_depending_on_singleton_is_fine(validator):
    registry = ServiceRegistry()
    registry.register("singleton_thing", lambda r: object(), lifetime=Lifetime.SINGLETON)
    registry.register(
        "session_thing", lambda r: object(), lifetime=Lifetime.SESSION,
        dependencies=["singleton_thing"],
    )
    assert validator.validate(registry) == []


def test_duplicate_canonical_role_is_an_error(validator):
    registry = ServiceRegistry()
    registry.register("impl_a", lambda r: object(), lifetime=Lifetime.SINGLETON, canonical_for="RoleX")
    registry.register("impl_b", lambda r: object(), lifetime=Lifetime.SINGLETON, canonical_for="RoleX")
    issues = validator.validate(registry)
    role_issues = [i for i in issues if i.code == "DUPLICATE_CANONICAL_IMPLEMENTATION"]
    assert len(role_issues) == 1
    assert role_issues[0].severity is IssueSeverity.ERROR


def test_distinct_canonical_roles_are_fine(validator):
    registry = ServiceRegistry()
    registry.register("impl_a", lambda r: object(), lifetime=Lifetime.SINGLETON, canonical_for="RoleX")
    registry.register("impl_b", lambda r: object(), lifetime=Lifetime.SINGLETON, canonical_for="RoleY")
    assert validator.validate(registry) == []


def test_deprecated_service_is_a_warning_not_an_error(validator):
    registry = ServiceRegistry()
    registry.register("legacy", lambda r: object(), lifetime=Lifetime.SINGLETON, deprecated=True)
    issues = validator.validate(registry)
    assert len(issues) == 1
    assert issues[0].severity is IssueSeverity.WARNING
    assert issues[0].code == "DEPRECATED_SERVICE"


def test_validate_or_raise_passes_silently_on_valid_graph(validator):
    registry = ServiceRegistry()
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON)
    validator.validate_or_raise(registry)  # must not raise


def test_validate_or_raise_raises_with_all_errors_on_invalid_graph(validator):
    registry = ServiceRegistry()
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["missing1"])
    registry.register("b", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["missing2"])
    with pytest.raises(DependencyGraphInvalidError) as exc:
        validator.validate_or_raise(registry)
    assert len(exc.value.issues) == 2


def test_validate_or_raise_ignores_warnings():
    registry = ServiceRegistry()
    registry.register("legacy", lambda r: object(), lifetime=Lifetime.SINGLETON, deprecated=True)
    DependencyGraphValidator().validate_or_raise(registry)  # must not raise — only a WARNING
