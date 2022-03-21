# flake8: noqa
import asyncio

from aiohttp import web

from repour import websockets


async def handle_socket(request):
    """ Websocket handler for live logs. Expects to receive the callback_id
        as part of the request

        Request: ws://<link>/ws/<callback_id>
    """

    callback_id = request.match_info["callback_id"]
    ws_obj = web.WebSocketResponse(autoping=True)

    await ws_obj.prepare(request)
    await websockets.register(callback_id, asyncio.current_task(), ws_obj)

    # Keep websocket alive if client hasn't closed it yet
    while True:
        if not ws_obj.closed:
            await asyncio.sleep(10)
        else:
            break

    return ws
