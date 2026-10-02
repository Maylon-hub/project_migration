"""Safe errors never retain raw requests, responses, headers or original exceptions."""


class PloneError(Exception):
    message = "REST request failed"

    def __init__(
        self,
        *,
        status: int | None = None,
        kind: str | None = None,
        message: str | None = None,
        content_type: str | None = None,
    ) -> None:
        self.status = status
        self.kind = kind or type(self).__name__
        self.message = message or type(self).message
        self.content_type = content_type
        super().__init__(self.message)

    def as_dict(self) -> dict:
        return {
            "type": self.kind,
            "message": self.message,
            "http_status": self.status,
            "content_type": self.content_type,
        }


class InventoryError(PloneError):
    """Local input/coverage failure using the same safe error boundary as transport."""

    def __init__(self, kind: str, message: str, status=None, content_type=None):
        super().__init__(kind=kind, message=message, status=status, content_type=content_type)


class AuthenticationError(PloneError):
    message = "Authentication required (401)"


class PermissionDeniedError(PloneError):
    message = "Access denied (403)"


class NotFoundError(PloneError):
    message = "Content not found (404)"


class RateLimitError(PloneError):
    message = "Rate limit reached (429)"


class ServerError(PloneError):
    message = "REST server error"


class RequestTimeoutError(PloneError):
    message = "REST request timed out"


class InvalidJSONError(PloneError):
    message = "REST response is not a JSON object or list of objects"


class TransportError(PloneError):
    message = "REST transport failed"


class UnsafeURLError(PloneError):
    message = "URL is outside the configured HTTPS site or is unsafe"


class EndpointUnconfirmedError(PloneError):
    message = "REST endpoint has not been configured or discovered"


class RedirectError(PloneError):
    message = "Redirect refused; validate the REST endpoint explicitly"


class PaginationError(PloneError):
    message = "Invalid or incomplete REST pagination"
