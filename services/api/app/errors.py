from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def not_found(resource: str = "资源") -> AppError:
    return AppError("NOT_FOUND", f"{resource}不存在或无权访问", 404)


def forbidden(message: str = "没有执行此操作的权限") -> AppError:
    return AppError("FORBIDDEN", message, 403)


def consent_required(message: str = "需要老人明确授权后才能执行此操作") -> AppError:
    return AppError("CONSENT_REQUIRED", message, 403)
