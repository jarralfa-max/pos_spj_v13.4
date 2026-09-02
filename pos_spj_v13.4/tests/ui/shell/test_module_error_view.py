from frontend.desktop.shell.loading.module_error_view import ModuleErrorView, build_module_error_view


def test_shows_module_id_and_error_in_message():
    view = build_module_error_view("inventory", RuntimeError("db offline"))
    assert isinstance(view, ModuleErrorView)
    assert view.module_id == "inventory"
    assert "db offline" in str(view.error)


def test_without_on_retry_there_is_no_retry_button():
    view = build_module_error_view("inventory", RuntimeError("x"))
    assert view.retry_button is None


def test_with_on_retry_clicking_the_button_invokes_the_callback():
    calls = []
    view = build_module_error_view("inventory", RuntimeError("x"), on_retry=lambda: calls.append(1))
    assert view.retry_button is not None
    view.retry_button.click()
    assert calls == [1]
