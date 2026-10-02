"""Exact origin and site-boundary checks precede every authenticated GET."""

from __future__ import annotations

from urllib.parse import parse_qsl, unquote, urljoin, urlsplit

from .errors import UnsafeURLError


def safe_url(base_url: str, path_or_url: str, *, endpoint: str | None = None) -> str:
    if not isinstance(path_or_url, str) or any(c.isspace() for c in path_or_url):
        raise UnsafeURLError()
    if "\\" in path_or_url or path_or_url.startswith("//"):
        raise UnsafeURLError()
    try:
        raw_path = urlsplit(path_or_url).path
    except ValueError:
        raise UnsafeURLError() from None
    if any(segment in (".", "..") for segment in raw_path.split("/")):
        raise UnsafeURLError()
    try:
        base = urlsplit(base_url)
        supplied = urlsplit(path_or_url)
        if not path_or_url:
            target = (endpoint or base_url).rstrip("/")
        elif supplied.scheme or supplied.netloc:
            target = path_or_url
        elif path_or_url.startswith("/"):
            # Inputs are site-relative, unless they already contain the full site prefix.
            site_path = base.path.rstrip("/")
            if site_path and (
                supplied.path == site_path or supplied.path.startswith(site_path + "/")
            ):
                target = f"{base.scheme}://{base.netloc}{path_or_url}"
            else:
                target = (endpoint or base_url).rstrip("/") + path_or_url
        elif path_or_url.startswith("?"):
            target = (endpoint or base_url).rstrip("/") + path_or_url
        else:
            target = urljoin((endpoint or base_url).rstrip("/") + "/", path_or_url)
        parts = urlsplit(target)
        origin = (parts.scheme, parts.hostname, parts.port or 443)
        allowed = (base.scheme, base.hostname, base.port or 443)
    except ValueError:
        raise UnsafeURLError() from None
    if origin != allowed or parts.scheme != "https" or parts.username or parts.password:
        raise UnsafeURLError()
    if parts.fragment or "\\" in parts.path:
        raise UnsafeURLError()
    decoded = parts.path
    for _ in range(4):
        new = unquote(decoded)
        if new == decoded:
            break
        decoded = new
    site = base.path.rstrip("/")
    if site and decoded != site and not decoded.startswith(site + "/"):
        raise UnsafeURLError()
    if (
        any(
            seg in (".", "..", "@login", "@login-renew", "@logout", "@lock")
            for seg in decoded.split("/")
        )
        or "\\" in decoded
        or any(ord(c) < 32 for c in decoded)
        or "%" in decoded
        or "//" in decoded
        or ("@workflow" in decoded.split("/") and decoded.split("/")[-1] != "@workflow")
        or any(
            any(
                s in key.lower() for s in ("token", "secret", "password", "cookie", "authorization")
            )
            for key, _ in parse_qsl(parts.query)
        )
    ):
        raise UnsafeURLError()
    return target
