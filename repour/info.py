import logging
from aiohttp import web

logger = logging.getLogger(__name__)

#
# Info/Documentation endpoint
#

# @asyncio.coroutine
class InfoEndpoint:
    info_data = None

    @staticmethod
    def handle(request):
        if InfoEndpoint.info_data is None:
            InfoEndpoint.info_data = ""
            with open("README.html", "r") as file:
                InfoEndpoint.info_data += file.read()
        return web.Response(body = InfoEndpoint.info_data.encode('utf-8'))
