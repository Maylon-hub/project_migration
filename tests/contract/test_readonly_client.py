import pytest
import requests

from studybr.api.client import ReadOnlyClient
from studybr.api.errors import (
    AuthenticationError,
    EndpointUnconfirmedError,
    InvalidJSONError,
    NotFoundError,
    PaginationError,
    PermissionDeniedError,
    RateLimitError,
    RedirectError,
    RequestTimeoutError,
    ServerError,
    TransportError,
    UnsafeURLError,
)
from studybr.settings import Settings


class FakeResponse:
    def __init__(self, status=200, data=None, bad_json=False):
        self.status_code = status
        self.data = data if data is not None else {"@type": "Document"}
        self.bad_json = bad_json

    def json(self):
        if self.bad_json:
            raise ValueError("Bearer opaque-secret Authorization: private")
        return self.data


class FakeSession:
    def __init__(self, responses=()):
        self.headers = {}
        self.cookies = {}
        self.auth = None
        self.calls = []
        self.responses = list(responses)

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        pass


def client(responses=(), rest_path=""):
    session = FakeSession(responses)
    settings = Settings("https://plone.example/site", "opaque-secret", rest_path=rest_path)
    return ReadOnlyClient(settings, session=session), session


def test_constructor_has_no_io_or_mutation_methods():
    api, session = client(rest_path=None)
    assert session.calls == []
    for name in ["post", "patch", "put", "delete", "login", "refresh", "workflow"]:
        assert not hasattr(api, name)
    with pytest.raises(EndpointUnconfirmedError):
        api.get("pt-br")
    assert session.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/site",
        "https://plone.example.evil/site",
        "https://plone.example/site-other",
        "http://plone.example/site",
        "//evil.example/site",
        "https://opaque-secret@plone.example/site",
        "https://plone.example:444/site",
        "/../escape",
        "/%2e%2e/escape",
        "https://plone.example/site/%252e%252e/escape",
        "pt-br\\evil",
        "@login",
        "@workflow/publish",
        "pt-br/@lock",
        "https://plone.example/site#fragment",
    ],
)
def test_unsafe_urls_never_receive_bearer(url):
    api, session = client()
    with pytest.raises(UnsafeURLError) as raised:
        api.get(url)
    assert "opaque-secret" not in str(raised.value)
    assert session.calls == []


@pytest.mark.parametrize(
    "path,expected",
    [
        ("pt-br", "https://plone.example/site/pt-br"),
        ("/pt-br", "https://plone.example/site/pt-br"),
        ("/site/pt-br", "https://plone.example/site/pt-br"),
        ("https://plone.example/site/pt-br", "https://plone.example/site/pt-br"),
    ],
)
def test_url_contract_without_presuming_api_traversal(path, expected):
    api, session = client([FakeResponse()])
    api.get(path)
    url, options = session.calls[0]
    assert url == expected
    assert options["verify"] is True
    assert options["timeout"] == (10.0, 30.0)
    assert options["allow_redirects"] is False
    assert options["headers"]["Authorization"] == "Bearer opaque-secret"


def test_configured_endpoint_is_used_only_when_explicit():
    api, session = client([FakeResponse()], rest_path="/rest")
    api.get("en")
    assert session.calls[0][0] == "https://plone.example/site/rest/en"


def test_discovery_is_explicit_get_only():
    api, session = client(
        [
            FakeResponse(404),
            FakeResponse(
                data={"@id": "https://plone.example/site", "@type": "Plone Site", "items": []}
            ),
            FakeResponse(),
        ],
        rest_path=None,
    )
    assert api.discover(["/candidate", ""]) == "https://plone.example/site"
    api.get("pt-br")
    assert len(session.calls) == 3


@pytest.mark.parametrize(
    "status,error",
    [
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServerError),
        (302, RedirectError),
    ],
)
def test_typed_http_errors(status, error, caplog):
    api, session = client([FakeResponse(status)])
    with pytest.raises(error) as raised:
        api.get("pt-br")
    assert raised.value.status == status
    assert "opaque-secret" not in str(raised.value)
    assert "Authorization" not in caplog.text
    assert "opaque-secret" not in caplog.text
    assert len(session.calls) == 1  # No unsafe retry or redirect.


@pytest.mark.parametrize(
    "response,error",
    [
        (requests.Timeout("Bearer opaque-secret"), RequestTimeoutError),
        (requests.ConnectionError("Cookie: opaque-secret"), TransportError),
        (FakeResponse(bad_json=True), InvalidJSONError),
        (FakeResponse(data=[1, 2]), InvalidJSONError),
    ],
)
def test_exception_context_does_not_retain_secret(response, error):
    api, _ = client([response])
    with pytest.raises(error) as raised:
        api.get()
    assert raised.value.__context__ is None
    assert "opaque-secret" not in repr(raised.value)


def test_pagination_reads_all_pages():
    api, session = client(
        [
            FakeResponse(
                data={"items": [{"id": "a"}], "items_total": 2, "batching": {"next": "?b_start=1"}}
            ),
            FakeResponse(data={"items": [{"id": "b"}], "items_total": 2}),
        ]
    )
    assert list(api.iter_items("pt-br")) == [{"id": "a"}, {"id": "b"}]
    assert session.calls[1][0] == "https://plone.example/site/pt-br?b_start=1"


@pytest.mark.parametrize("next_page", ["https://evil.example/page", "//evil.example/page"])
def test_external_pagination_blocked_before_second_request(next_page):
    api, session = client([FakeResponse(data={"items": [], "batching": {"next": next_page}})])
    with pytest.raises(UnsafeURLError):
        list(api.iter_items())
    assert len(session.calls) == 1


def test_incomplete_or_looping_pagination_is_error():
    api, _ = client([FakeResponse(data={"items": [], "items_total": 5})])
    with pytest.raises(PaginationError):
        list(api.iter_items())
    api, _ = client(
        [FakeResponse(data={"items": [], "batching": {"next": "https://plone.example/site"}})]
    )
    with pytest.raises(PaginationError):
        list(api.iter_items())


def test_netrc_and_session_cookies_are_not_used():
    api, session = client([FakeResponse()])
    session.cookies.update({"session": "private-cookie"})
    api.get()
    assert session.cookies == {}
    assert session.auth is not None  # Explicit auth prevents requests from consulting .netrc.
