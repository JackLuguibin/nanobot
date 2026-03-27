"""API response wrappers and error codes."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

API_CODE_SUCCESS = 0


class ApiErrorCode:
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE = 422
    SERVICE_UNAVAILABLE = 503
    INTERNAL_ERROR = 500


class ApiSuccessResponse(BaseModel, Generic[T]):
    """成功响应信封：code=0, message, data"""

    code: int = Field(default=API_CODE_SUCCESS, description="成功时为 0")
    message: str = Field(default="success", description="成功描述")
    data: Any = None


class ApiErrorResponse(BaseModel):
    """错误响应：code 为错误码，message 为错误原因"""

    code: int = Field(..., description="错误码")
    message: str = Field(..., description="错误原因，供前端直接展示")
