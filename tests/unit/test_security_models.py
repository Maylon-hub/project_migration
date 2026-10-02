import io
import json
import logging
import unicodedata

import pytest

from studybr.models import EditorialPolicy, Institution, LocalizedPage, PageKind, normalize_acronym
from studybr.security import RedactingFormatter, Redactor
from studybr.settings import ConfigurationError, Settings


def test_redaction_covers_nested_values_keys_and_known_secrets():
    redactor = Redactor(("opaque-secret",))
    data = redactor.data(
        {
            "authorization": "anything",
            "cookies": ["private"],
            "nested": ["name opaque-secret", "Bearer another-value"],
        }
    )
    rendered = str(data)
    assert "opaque-secret" not in rendered
    assert "another-value" not in rendered
    assert "anything" not in rendered
    assert "private" not in rendered


def test_log_exception_is_redacted_at_final_formatting():
    sink = io.StringIO()
    handler = logging.StreamHandler(sink)
    handler.setFormatter(RedactingFormatter(Redactor(("opaque-secret",))))
    logger = logging.Logger("redaction-test")
    logger.addHandler(handler)
    try:
        raise ValueError("Bearer unknown-value Cookie: private-cookie opaque-secret")
    except ValueError:
        logger.exception("failure %s", "opaque-secret")
    assert not any(
        s in sink.getvalue() for s in ["opaque-secret", "unknown-value", "private-cookie"]
    )
    entry = json.loads(sink.getvalue())
    assert entry["level"] == "ERROR"
    assert entry["logger"] == "redaction-test"
    assert "ValueError" in entry["exception"]


def test_quoted_cookie_and_basic_auth_headers_are_redacted():
    redactor = Redactor()
    for data in [{"Cookie": "opaque-cookie"}, {"Authorization": "Basic opaque-basic"}]:
        output = redactor.text(str(data))
        assert "opaque-cookie" not in output
        assert "opaque-basic" not in output


@pytest.mark.parametrize("timeout", [(0, 10), (10, -1), (float("nan"), 10), (10, float("inf"))])
def test_timeout_must_be_finite_and_positive(timeout):
    with pytest.raises(ConfigurationError):
        Settings("https://example.test/site", "opaque-secret", timeout=timeout)


def test_configured_https_port_is_part_of_origin():
    assert Settings("https://example.test:8443/site", "opaque-secret").base_url.endswith(
        ":8443/site"
    )


def test_credentials_never_have_fallback_or_repr_leak():
    with pytest.raises(ConfigurationError):
        Settings.from_env(environ={})
    settings = Settings.from_env(
        environ={"PLONE_BASE_URL": "https://example.test/site", "PLONE_TOKEN": "opaque-secret"}
    )
    assert "opaque-secret" not in repr(settings)
    with pytest.raises(ConfigurationError):
        Settings("http://example.test/site", "opaque-secret")


@pytest.mark.parametrize(
    "value,expected", [(" UFSCar ", "UFSCAR"), ("CEFET_MG", "CEFET-MG"), ("CEFET-MG", "CEFET-MG")]
)
def test_acronym_normalization_and_aliases(value, expected):
    assert normalize_acronym(value) == expected


def test_unicode_quotes_and_nulls_are_domain_data():
    title = unicodedata.normalize("NFD", 'Instituição "São José"')
    page = LocalizedPage(PageKind.ABOUT, "pt-br", title=title)
    institution = Institution("br-test", "TEST", official_name='Instituição "São José"')
    assert institution.official_name.endswith('"São José"')
    assert page.description is None
    assert page.semantic_id == "about"
    with pytest.raises(ValueError):
        EditorialPolicy(ownership="overwrite-everything")
