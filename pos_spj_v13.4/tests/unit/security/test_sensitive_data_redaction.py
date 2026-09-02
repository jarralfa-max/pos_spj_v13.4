import logging

from backend.security.audit.sensitive_data_redaction import (
    SensitiveDataRedactionFilter,
    redact_mapping,
    redact_text,
)


def test_redact_mapping_masks_password_key():
    data = {"username": "juan", "password": "s3cret!"}
    redacted = redact_mapping(data)
    assert redacted["username"] == "juan"
    assert redacted["password"] == "***REDACTED***"


def test_redact_mapping_masks_known_variants():
    data = {
        "pin": "1234",
        "api_key": "sk_live_abc",
        "authorization": "Bearer xyz",
        "secret": "top-secret",
        "card_number": "4111111111111111",
        "client_secret": "cs_abc",
    }
    redacted = redact_mapping(data)
    assert all(v == "***REDACTED***" for v in redacted.values())


def test_redact_mapping_is_recursive():
    data = {"user": {"name": "juan", "password_hash": "abc"}, "items": [{"token": "xyz"}]}
    redacted = redact_mapping(data)
    assert redacted["user"]["password_hash"] == "***REDACTED***"
    assert redacted["user"]["name"] == "juan"
    assert redacted["items"][0]["token"] == "***REDACTED***"


def test_redact_mapping_does_not_mutate_input():
    data = {"password": "s3cret!"}
    redact_mapping(data)
    assert data["password"] == "s3cret!"


def test_redact_mapping_passes_through_non_sensitive_data():
    data = {"total": 123.45, "sucursal_id": "abc-123"}
    assert redact_mapping(data) == data


def test_redact_text_masks_inline_key_value():
    text = "login attempt password=admin123 for user juan"
    redacted = redact_text(text)
    assert "admin123" not in redacted
    assert "***REDACTED***" in redacted


def test_redact_text_masks_json_like_fragment():
    text = '{"token": "abc.def.ghi", "user": "juan"}'
    redacted = redact_text(text)
    assert "abc.def.ghi" not in redacted
    assert "juan" in redacted


def test_redact_text_passes_through_clean_text():
    text = "Usuario juan inició sesión correctamente."
    assert redact_text(text) == text


def test_filter_redacts_dict_message():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg={"password": "s3cret!"}, args=None, exc_info=None,
    )
    SensitiveDataRedactionFilter().filter(record)
    assert record.msg["password"] == "***REDACTED***"


def test_filter_redacts_string_message():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="login failed password=admin123", args=None, exc_info=None,
    )
    SensitiveDataRedactionFilter().filter(record)
    assert "admin123" not in record.msg


def test_filter_redacts_string_args():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="attempt: %s", args=("password=admin123",), exc_info=None,
    )
    SensitiveDataRedactionFilter().filter(record)
    assert "admin123" not in record.args[0]


def test_filter_returns_true_to_allow_propagation():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="ok", args=None, exc_info=None,
    )
    assert SensitiveDataRedactionFilter().filter(record) is True
