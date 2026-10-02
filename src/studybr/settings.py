"""Explicit environment credentials. No fallback, login or discovery side effects."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    pass


def validate_base_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError:
        raise ConfigurationError("Invalid PLONE_BASE_URL") from None
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or any(c.isspace() for c in value)
        or "\\" in value
        or "%" in parts.path
        or "//" in parts.path
        or any(p in (".", "..") for p in parts.path.split("/"))
    ):
        raise ConfigurationError("PLONE_BASE_URL must be an HTTPS site URL without credentials")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    base_url: str
    token: str = field(repr=False)
    rest_path: str | None = None
    timeout: tuple[float, float] = (10.0, 30.0)
    max_requests: int = 100
    max_response_bytes: int = 10 * 1024 * 1024

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", validate_base_url(self.base_url))
        token = self.token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if not token or any(c.isspace() for c in token):
            raise ConfigurationError("PLONE_TOKEN must contain a nonempty credential")
        object.__setattr__(self, "token", token)
        if len(self.timeout) != 2 or any(not math.isfinite(t) or t <= 0 for t in self.timeout):
            raise ConfigurationError("Timeouts must be positive")
        if self.max_requests <= 0 or self.max_response_bytes <= 0:
            raise ConfigurationError("Request and response limits must be positive")

    @classmethod
    def from_env(
        cls,
        *,
        rest_path: str | None = None,
        environ: Mapping[str, str] | None = None,
        timeout: tuple[float, float] = (10.0, 30.0),
        max_requests: int = 100,
    ) -> Settings:
        values = os.environ if environ is None else environ
        if not values.get("PLONE_BASE_URL") or not values.get("PLONE_TOKEN"):
            raise ConfigurationError("PLONE_BASE_URL and PLONE_TOKEN are required")
        return cls(
            values["PLONE_BASE_URL"].strip(),
            values["PLONE_TOKEN"],
            rest_path=rest_path,
            timeout=timeout,
            max_requests=max_requests,
        )
