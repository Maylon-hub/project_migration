"""The single GET-only transport for diagnostics and bounded portal inventory."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import requests

from studybr.security import Redactor
from studybr.settings import Settings

from .errors import (
    AuthenticationError,
    EndpointUnconfirmedError,
    InvalidJSONError,
    InventoryError,
    NotFoundError,
    PaginationError,
    PermissionDeniedError,
    PloneError,
    RateLimitError,
    RedirectError,
    RequestTimeoutError,
    ServerError,
    TransportError,
    UnsafeURLError,
)
from .urls import safe_url

logger = logging.getLogger(__name__)
_INVALID_JSON = object()


class _ExplicitHeaderAuth(requests.auth.AuthBase):
    def __call__(self, request):
        return request


class ReadOnlyClient:
    def __init__(self, settings: Settings, *, session: Any = None) -> None:
        self._settings = settings
        self._session = session if session is not None else requests.Session()
        self._session.auth = _ExplicitHeaderAuth()
        self._session.headers.clear()
        self._session.cookies.clear()
        self._session.trust_env = False
        self._site_url = settings.base_url.removesuffix("/++api++")
        self._endpoint = (
            safe_url(self._site_url, settings.rest_path, endpoint=settings.base_url)
            if settings.rest_path is not None
            else None
        )
        self.base_url = self._endpoint or settings.base_url
        self.frontend_url = self._site_url
        self._redactor = Redactor((settings.token,))
        self._stopped = False
        self.requests_made = 0

    def resolve(self, path: str) -> str:
        if isinstance(path, str) and (
            self._settings.token in unquote(path) or "[redacted]" in path.lower()
        ):
            raise UnsafeURLError()
        # Absolute frontend @ids remain exactly as observed, without traversal rewriting.
        return safe_url(self._site_url, path, endpoint=self._endpoint)

    def path_of(self, path: str) -> str:
        target = urlsplit(self.resolve(path)).path
        for root in (urlsplit(self.base_url).path, urlsplit(self.frontend_url).path):
            if target == root or target.startswith(root + "/"):
                return target[len(root) :] or "/"
        raise UnsafeURLError()

    def redact(self, value):
        return self._redactor.public_data(value)

    def _transport(self, target):
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._settings.token}"}
        self._session.cookies.clear()
        if isinstance(self._session, requests.Session):
            prepared = requests.Request("GET", target, headers=headers).prepare()
            return self._session.send(
                prepared,
                timeout=self._settings.timeout,
                verify=True,
                allow_redirects=False,
                proxies={},
                stream=True,
            )
        return self._session.get(
            target,
            headers=headers,
            timeout=self._settings.timeout,
            verify=True,
            allow_redirects=False,
        )

    def _read_json(self, response):
        if isinstance(response, requests.Response):
            chunks = []
            size = 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > self._settings.max_response_bytes:
                    raise InventoryError(
                        "response_limit", "Response exceeds the configured byte limit."
                    )
                chunks.append(chunk)
            result = _INVALID_JSON
            try:
                result = json.loads(b"".join(chunks))
            except (ValueError, UnicodeError):
                pass
            return result
        result = _INVALID_JSON
        try:
            result = response.json()
        except Exception:
            pass
        return result

    def _get_url(self, url: str):
        if self._stopped:
            raise AuthenticationError(status=401, kind="authentication_stopped")
        if self.requests_made >= self._settings.max_requests:
            raise InventoryError("request_limit", "Request limit reached; inventory is partial.")
        target = self.resolve(url)
        self.requests_made += 1
        failure = None
        response = None
        try:
            response = self._transport(target)
        except requests.Timeout:
            failure = RequestTimeoutError()
        except Exception:
            failure = TransportError()
        if failure is not None:
            raise failure from None
        try:
            status = response.status_code
            logger.info("REST GET status=%d", status)
            headers = getattr(response, "headers", {"Content-Type": "application/json"})
            content_type = self._redactor.error_text(headers.get("Content-Type", ""))
            if status == 401:
                self._stopped = True
                raise AuthenticationError(
                    status=401, kind="unauthorized", content_type=content_type
                )
            if 300 <= status < 400:
                raise RedirectError(
                    status=status, kind="redirect_blocked", content_type=content_type
                )
            errors = {403: PermissionDeniedError, 404: NotFoundError, 429: RateLimitError}
            error_type = errors.get(status, ServerError if status >= 500 else PloneError)
            media_type = content_type.split(";", 1)[0].strip().lower()
            is_json = media_type in {
                "application/json",
                "application/json+schema",
            } or media_type.endswith("+json")
            if not is_json:
                if status != 200:
                    raise error_type(status=status, content_type=content_type)
                raise InvalidJSONError(status=status, kind="non_json", content_type=content_type)
            result = self._read_json(response)
            if status != 200:
                kind = (
                    self._redactor.error_text(result.get("type"))
                    if isinstance(result, dict)
                    else ""
                )
                message = (
                    self._redactor.error_text(result.get("message"))
                    if isinstance(result, dict)
                    else ""
                )
                raise error_type(
                    status=status,
                    kind=kind or None,
                    message=message or None,
                    content_type=content_type,
                )
            if result is _INVALID_JSON:
                raise InvalidJSONError(
                    status=status, kind="invalid_json", content_type=content_type
                )
            if not isinstance(result, (dict, list)) or (
                isinstance(result, list) and not all(isinstance(item, dict) for item in result)
            ):
                raise InvalidJSONError(
                    status=status, kind="invalid_shape", content_type=content_type
                )
            return self.redact(result)
        except requests.RequestException:
            failure = TransportError()
        finally:
            self._session.cookies.clear()
            if hasattr(response, "close"):
                response.close()
        raise failure from None

    def request(self, method: str, path: str = ""):
        if method != "GET":
            raise InventoryError("method_blocked", "Only GET is permitted.")
        return self.get(path)

    def get(self, path_or_url: str = ""):
        if self._endpoint is None:
            raise EndpointUnconfirmedError()
        return self._get_url(self.resolve(path_or_url))

    def discover(self, candidates: Sequence[str]) -> str:
        for candidate in candidates:
            url = self.resolve(candidate)
            try:
                data = self._get_url(url)
            except (NotFoundError, InvalidJSONError):
                continue
            if not isinstance(data, dict):
                continue
            context = data.get("@id")
            if context and data.get("@type") and isinstance(data.get("items"), list):
                self.resolve(context)
                self._endpoint = url
                self.base_url = url
                return url
        raise EndpointUnconfirmedError()

    def next_url(self, current: str, next_page: str) -> str:
        """Only a server batch link within the same collection is admissible."""
        if not isinstance(next_page, str):
            raise PaginationError()
        if next_page.startswith("?"):
            parts = urlsplit(self.resolve(current))
            target = self.resolve(urlunsplit(parts._replace(query=next_page[1:])))
        else:
            target = self.resolve(next_page)
        if self.path_of(target) != self.path_of(current):
            raise InventoryError("unsafe_pagination", "Batch link leaves the observed collection.")
        return target

    def iter_items(self, path_or_url: str = "", *, max_pages: int = 10000) -> Iterator[Mapping]:
        if self._endpoint is None:
            raise EndpointUnconfirmedError()
        current = self.resolve(path_or_url)
        visited = set()
        identities = set()
        total = None
        count = 0
        for _ in range(max_pages):
            if current in visited:
                raise PaginationError()
            visited.add(current)
            data = self._get_url(current)
            if not isinstance(data, dict):
                raise PaginationError()
            items = data.get("items")
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise PaginationError()
            if "items_total" in data:
                reported = data["items_total"]
                if not isinstance(reported, int) or isinstance(reported, bool) or reported < 0:
                    raise PaginationError()
                if total is not None and total != reported:
                    raise PaginationError()
                total = reported
            for item in items:
                identity = item.get("@id") or item.get("UID") or item.get("id")
                if isinstance(identity, str):
                    if identity in identities:
                        raise PaginationError()
                    identities.add(identity)
            count += len(items)
            yield from items
            batching = data.get("batching", {})
            if not isinstance(batching, dict):
                raise PaginationError()
            next_page = batching.get("next")
            if not next_page:
                if total is not None and total != count:
                    raise PaginationError()
                return
            if not isinstance(next_page, str):
                raise PaginationError()
            current = self.next_url(current, next_page)
        raise PaginationError()

    def close(self):
        self._session.close()
