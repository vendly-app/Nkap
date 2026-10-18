"""Éléments communs aux API (site et central) : format des erreurs, taille des requêtes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.responses import Response

from nkap.core.errors import NkapError
from nkap.i18n import translate

MAX_BODY_BYTES = 8 * 1024 * 1024
"""Taille maximale d'une requête (8 Mo) : protège le serveur des envois démesurés."""


def request_locale(request: Request) -> str:
    """Langue de l'utilisateur (en-tête ``Accept-Language``), français par défaut."""
    header = request.headers.get("accept-language", "fr").strip().lower()
    return "en" if header.startswith("en") else "fr"


def error_response(
    status: int, code: str, message: str, details: list[str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or []}},
    )


def _invalid(request: Request, errors: Sequence[Any]) -> JSONResponse:
    details = [
        f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg', '')}" for err in errors
    ]
    message = translate("request.invalid", request_locale(request))
    return error_response(422, "request.invalid", message, details)


def install_error_handlers(app: FastAPI) -> None:
    """Toutes les erreurs de l'API ont la même forme : ``{"error": {code, message, details}}``."""

    @app.exception_handler(NkapError)
    async def _nkap_error(request: Request, exc: NkapError) -> JSONResponse:
        return error_response(exc.http_status, exc.code, exc.message(request_locale(request)))

    @app.exception_handler(RequestValidationError)
    async def _request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _invalid(request, exc.errors())

    @app.exception_handler(ValidationError)
    async def _validation_error(request: Request, exc: ValidationError) -> JSONResponse:
        return _invalid(request, exc.errors())

    @app.middleware("http")
    async def _limit_body_size(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        length = request.headers.get("content-length")
        if length is not None and length.isdigit() and int(length) > MAX_BODY_BYTES:
            message = translate("request.too_large", request_locale(request))
            return error_response(413, "request.too_large", message)
        return await call_next(request)
