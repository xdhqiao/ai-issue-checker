from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApplicationError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ApplicationError):
    status_code = 404


class ConflictError(ApplicationError):
    status_code = 409


class PayloadTooLargeError(ApplicationError):
    status_code = 413


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def handle_application_error(_request: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
