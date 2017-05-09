import asyncio
import logging

from .. import websockets

class WebsocketLoggerHandler(logging.Handler):

    def emit(self, record):
        try:
            msg = self.format(record)
            task = asyncio.Task.current_task()

            if task is not None:
                callback_id = getattr(task, "callback_id", None)
                if callback_id is not None:
                    asyncio.get_event_loop().create_task(
                    websockets.send(callback_id, msg))
        except:
            self.handleError(record)