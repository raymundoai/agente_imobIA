class ApplicationError(Exception):
    status_code = 400
    code = "application_error"


class NotFoundError(ApplicationError):
    status_code = 404
    code = "not_found"


class ConflictError(ApplicationError):
    status_code = 409
    code = "conflict"


class ForbiddenError(ApplicationError):
    status_code = 403
    code = "forbidden"


class AuthenticationError(ApplicationError):
    status_code = 401
    code = "authentication_failed"


class ExternalServiceError(ApplicationError):
    status_code = 502
    code = "external_service_error"


class ConfigurationError(ApplicationError):
    status_code = 503
    code = "configuration_error"


class TooManyRequestsError(ApplicationError):
    status_code = 429
    code = "too_many_requests"

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class PaymentRequiredError(ApplicationError):
    status_code = 402
    code = "credits_required"
