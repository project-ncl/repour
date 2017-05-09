import asyncio

from aiohttp import web
from ... import websockets


@asyncio.coroutine
def handle_socket(request):
    """ Websocket handler for live logs. Expects to receive the callback_id
        as part of the request

        Request: ws://<link>/ws/<callback_id>
    """

    callback_id = request.match_info['callback_id']
    ws_obj = web.WebSocketResponse(autoping=True)

    yield from ws_obj.prepare(request)
    yield from websockets.register(callback_id, asyncio.Task.current_task(), ws_obj)

    # Keep websocket alive if client hasn't closed it yet
    while True:
        if not ws_obj.closed:
            yield from asyncio.sleep(10)
        else:
            break

    return ws
