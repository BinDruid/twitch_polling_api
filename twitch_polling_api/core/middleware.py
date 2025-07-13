import datetime
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse, Response
from fastapi.security.utils import get_authorization_scheme_param
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError, JWKError, JWTClaimsError
from pydantic import BaseModel, ValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request

from twitch_polling_api.core.config import settings

from .sentry import logger


class AnonymousUser:
    public_id = None

    @property
    def is_authenticated(self):
        return False

    @property
    def is_anonymous(self):
        return True


class AuthenticatedUser(BaseModel):
    public_id: str

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False


class NoAuthenticationHeaderError(Exception):
    pass


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        authorization: str = request.headers.get('Authorization')
        scheme, param = get_authorization_scheme_param(authorization)
        try:
            if not authorization or scheme.lower() != 'bearer':
                raise NoAuthenticationHeaderError()
            token = authorization.split()[1]
            data = jwt.decode(token, settings.JWT_SECRET)
            request.state.user = AuthenticatedUser(public_id=data['user_id'])
        except (NoAuthenticationHeaderError, JWKError, JWTError, JWTClaimsError, ExpiredSignatureError):
            request.state.user = AnonymousUser()
        response = await call_next(request)
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = datetime.datetime.utcnow()
        method_name = request.method.upper()
        url = request.url
        user = request.state.user.public_id or 'Anonymous'
        if '/healthcheck/' not in str(url):
            with open(f'{settings.PATHS.ROOT_DIR}/logs/requests.log', mode='a') as request_logs:
                log_id = str(uuid4())
                log_message = f'Log [{log_id}]\n[{start_time}] [User #{user}] [{method_name}] {url}\n'
                request_logs.write(log_message)
        response = await call_next(request)
        process_time = datetime.datetime.utcnow() - start_time
        response.headers['X-Process-Time'] = str(process_time)
        return response


class ExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> JSONResponse:
        try:
            response = await call_next(request)
        except HTTPException as http_exception:
            response = JSONResponse(
                status_code=http_exception.status_code, content={'detail': str(http_exception.detail)}
            )
        except ValidationError as e:
            response = JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={'detail': e.errors()})
        except Exception as e:  # noqa
            logger.exception(e)
            content = {'detail': [{'msg': 'Unknown', 'loc': ['Unknown'], 'type': 'Unknown'}]}
            if settings.DEBUG:
                content = {'detail': [{'error': e.__class__.__name__, 'mgs': e.args}]}
            response = JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=content)
        return response
