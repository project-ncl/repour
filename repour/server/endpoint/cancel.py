import asyncio
import json
import logging

from aiohttp import web

logger = logging.getLogger(__name__)

# Mock cancel endpoint

@asyncio.coroutine
def handle_cancel(request):
    response = web.Response(
        status=200
    )
    return response
