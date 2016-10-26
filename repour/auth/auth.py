import asyncio
import logging

import aiohttp.web

from . import oauth2_jwt

logger = logging.getLogger(__name__)


# Middleware handlers for auth

def fail(request):
    return aiohttp.web.Response(status=403)


@asyncio.coroutine
def get_oauth2_jwt_handler(app, next_handler):
    @asyncio.coroutine
    def handler(request):
        auth_header_value = request.headers.get('Authorization', None)
        prefix_length = len('Bearer ')

        if not auth_header_value or len(auth_header_value) <= prefix_length:
            return fail(request)

        token = auth_header_value[prefix_length:]
        token_verified = yield from oauth2_jwt.verify_token(token)
        if not token_verified:
            return fail(request)

        response = yield from next_handler(request)
        response.headers['Authorization'] = request.headers['Authorization']
        return response

    return handler


providers = {
    'oauth2_jwt': get_oauth2_jwt_handler
}
