"""统一 API 响应格式：成功码/错误码、错误原因，以及全局异常处理。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from console.server.api.models import API_CODE_SUCCESS, ApiErrorResponse


def _error_body(code: int, message: str) -> dict[str, Any]:
    """构建错误响应 body，供前端展示 message。"""
    return ApiErrorResponse(code=code, message=message).model_dump()


def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """将 HTTPException 转为统一错误格式：code + message。"""
    detail = exc.detail
    if isinstance(detail, list):
        message = "; ".join(str(x) for x in detail) if detail else "Request error"
    else:
        message = str(detail) if detail else "Request error"
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.status_code, message),
    )


def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """将未捕获异常转为 500 + 统一错误格式。"""
    return JSONResponse(
        status_code=500,
        content=_error_body(500, str(exc)),
    )


class SuccessEnvelopeMiddleware(BaseHTTPMiddleware):
    """为 200 的 JSON 响应包一层 { code, message, data }。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        # 只包装 /api 下的 200 且 application/json
        if request.url.path.startswith("/api") and response.status_code == 200:
            ct = response.headers.get("content-type") or ""
            if "application/json" in ct and "text/event-stream" not in ct:
                try:
                    body = b""
                    async for chunk in response.body_iterator:
                        body += chunk
                    data = json.loads(body.decode("utf-8"))
                    # 若已是信封格式则不再包装
                    if isinstance(data, dict) and "code" in data and "data" in data:
                        return JSONResponse(content=data)
                    wrapped = {
                        "code": API_CODE_SUCCESS,
                        "message": "success",
                        "data": data,
                    }
                    return JSONResponse(content=wrapped)
                except (json.JSONDecodeError, ValueError):
                    pass
        return response
