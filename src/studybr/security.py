"""Defensive redaction at logging, diagnostic serialization and CLI boundaries."""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Mapping
from enum import Enum
from typing import Any
from urllib.parse import quote

REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(r"token|secret|password|authorization|cookie", re.I)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_BEARER = re.compile(r"\bBearer\s+[^\s,;\"'<>]+", re.I)
_HEADER = re.compile(r"[\"']?\b(?:Authorization|Cookie|Set-Cookie)[\"']?\s*[:=][^\r\n]*", re.I)


class Redactor:
    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        self._secrets = tuple(sorted({s for s in secrets if s}, key=len, reverse=True))

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> Redactor:
        values = os.environ if environ is None else environ
        return cls(tuple(v for k, v in values.items() if _SENSITIVE_KEY.search(k) and v))

    def text(self, value: object) -> str:
        result = str(value)
        for secret in self._secrets:
            result = result.replace(secret, REDACTED).replace(quote(secret, safe=""), REDACTED)
        result = _HEADER.sub(REDACTED, result)
        result = _BEARER.sub(REDACTED, result)
        return _JWT.sub(REDACTED, result)

    def data(self, value: Any) -> Any:
        if isinstance(value, Enum):
            return self.data(value.value)
        if isinstance(value, Mapping):
            return {
                self.text(k): REDACTED if _SENSITIVE_KEY.search(str(k)) else self.data(v)
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self.data(v) for v in value]
        if isinstance(value, str):
            return self.text(value)
        return value

    def public_data(self, value: Any) -> Any:
        """Remove credential fields entirely from persisted HTTP response bodies."""
        if isinstance(value, Mapping):
            return {
                self.text(k): self.public_data(v)
                for k, v in value.items()
                if not _SENSITIVE_KEY.search(str(k))
            }
        if isinstance(value, (list, tuple)):
            return [self.public_data(v) for v in value]
        return self.data(value)

    def error_text(self, value: object) -> str:
        if not isinstance(value, str):
            return ""
        value = self.text(value)
        value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", REDACTED, value)
        return re.sub(r"[\x00-\x1f\x7f]", " ", value)[:240]


class RedactingFormatter(logging.Formatter):
    """Redacts the final message, including formatted exception tracebacks."""

    def __init__(self, redactor: Redactor) -> None:
        super().__init__("%(levelname)s %(message)s")
        self.redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        fields = {
            "level": record.levelname,
            "logger": self.redactor.text(record.name),
            "message": self.redactor.text(record.getMessage()),
        }
        if record.exc_info:
            fields["exception"] = self.redactor.text(self.formatException(record.exc_info))
        if record.stack_info:
            fields["stack"] = self.redactor.text(record.stack_info)
        return json.dumps(fields, ensure_ascii=False, sort_keys=True)


def configure_logging(redactor: Redactor | None = None) -> None:
    formatter = RedactingFormatter(redactor or Redactor.from_environment())
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for handler in root.handlers:
        handler.setFormatter(formatter)
    root.setLevel(logging.INFO)
