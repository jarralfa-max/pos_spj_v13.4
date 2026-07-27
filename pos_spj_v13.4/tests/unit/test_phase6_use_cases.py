from backend.application.commands import (
    CreateSaleCommand,
    DispatchTransferCommand,
    GeneratePurchasePlanCommand,
    RegisterWasteCommand,
)
from backend.application.dto import UseCaseResult
from backend.application.use_cases import (
    CreateSaleUseCase,
    DispatchTransferUseCase,
    GeneratePurchasePlanUseCase,
    RegisterWasteUseCase,
)


def _command(command_class, **payload):
    return command_class(
        operation_id="op-1",
        branch_id="branch-1",
        user_name="admin",
        payload=payload,
    )


def test_use_case_shell_delegates_to_injected_handler_without_business_logic() -> None:
    received = []

    def handler(command: CreateSaleCommand) -> UseCaseResult:
        received.append(command)
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id="sale-1")

    command = _command(CreateSaleCommand, total="100.00")
    result = CreateSaleUseCase(handler).execute(command)

    assert received == [command]
    assert result == UseCaseResult(success=True, operation_id="op-1", entity_id="sale-1")


def test_unwired_use_case_returns_not_implemented_result_for_gradual_transition() -> None:
    command = _command(RegisterWasteCommand, reason="caducidad")

    result = RegisterWasteUseCase().execute(command)

    assert result.success is False
    assert result.operation_id == "op-1"
    assert "RegisterWasteUseCase" in result.message


def test_use_case_validates_required_command_context() -> None:
    command = DispatchTransferCommand(operation_id="", branch_id="branch-1", user_name="admin")

    try:
        DispatchTransferUseCase().execute(command)
    except ValueError as exc:
        assert "operation_id" in str(exc)
    else:
        raise AssertionError("Use case should validate command context")


def test_priority_use_cases_are_available_with_canonical_names() -> None:
    use_cases = [
        CreateSaleUseCase,
        DispatchTransferUseCase,
        GeneratePurchasePlanUseCase,
        RegisterWasteUseCase,
    ]

    assert {use_case().name for use_case in use_cases} == {
        "CreateSaleUseCase",
        "DispatchTransferUseCase",
        "GeneratePurchasePlanUseCase",
        "RegisterWasteUseCase",
    }
