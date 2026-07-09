from fastapi import HTTPException, status


class D10Exception(Exception):
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(D10Exception):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} '{resource_id}' not found", "NOT_FOUND")


class UnauthorizedError(D10Exception):
    def __init__(self):
        super().__init__("Unauthorized", "UNAUTHORIZED")


class MetaAPIError(D10Exception):
    def __init__(self, message: str):
        super().__init__(f"Meta API error: {message}", "META_API_ERROR")


class TenantLimitError(D10Exception):
    def __init__(self):
        super().__init__("Tenant Meta account limit reached", "TENANT_LIMIT")


def raise_http(exc: D10Exception) -> None:
    status_map = {
        "NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "UNAUTHORIZED": status.HTTP_401_UNAUTHORIZED,
        "TENANT_LIMIT": status.HTTP_429_TOO_MANY_REQUESTS,
    }
    raise HTTPException(
        status_code=status_map.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        detail={"code": exc.code, "message": exc.message},
    )
