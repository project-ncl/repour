# flake8: noqa
import logging

import aiohttp.web

from repour.auth import oauth2_jwt

logger = logging.getLogger(__name__)


# Middleware handlers for auth


def fail(request, status=403):
    return aiohttp.web.Response(status=status)


async def get_oauth2_jwt_handler(app, next_handler):
    async def handler(request):

        if (
            request.path == "/"
            or request.path == "/git-external-to-internal"
            or request.path == "/metrics"
            or request.path == "/version"
        ):
            # we don't authenticate for request to '/'. We'll show relevant repour information there
            response = await next_handler(request)
            return response

        auth_header_value = request.headers.get("Authorization", None)
        prefix_length = len("Bearer ")

        if not auth_header_value or len(auth_header_value) <= prefix_length:
            return fail(request, status=401)

        token = auth_header_value[prefix_length:]
        token_verified = await oauth2_jwt.verify_token(token)
        if not token_verified:
            return fail(request)

        response = await next_handler(request)

        response.headers["Authorization"] = request.headers["Authorization"]
        return response

    return handler


providers = {"oauth2_jwt": get_oauth2_jwt_handler}
