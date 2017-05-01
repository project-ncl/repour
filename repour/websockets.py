import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Global object with key: callback_id and
# value (asyncio_task, websocket_handler)
websocket_handlers = {}

@asyncio.coroutine
def register(callback_id, task, websocket_handler):
    """ Register a websocket handler with a callback_id and the task where
        the websocket handler was spawn

        We are going to use this information in the `send` function to send
        log events for a particular callback to the appropriate websocket.

        We need to get the task because that's the only way to figure out if a
        websocket is closed or not. If the task is done, the websocket is closed

        Parameters:
        - callback_id: :str: id
        - task: :asyncio_task: task where websocket handler created
        - websocket_handler: :aiohttp_websocket: websocket handler

        Returns:
        - None
    """
    global websocket_handlers

    if callback_id not in websocket_handlers:
        websocket_handlers[callback_id] = [(task, websocket_handler)]
    else:
        websocket_handlers[callback_id].append((task, websocket_handler))


@asyncio.coroutine
def periodic_cleanup():
    """ Cleanup the websocket_handlers datastructure by removing closed
        websocket handlers and callback_ids with empty websocket list

        It runs every 30 seconds. It needs to be launched inside its own task

        Parameters:
        - None

        Returns:
        - None
    """
    global websocket_handlers

    while True:

        # find already closed websocket_handlers and remove them from list of
        # 'active' handlers
        for callback_id in websocket_handlers:
            handlers = websocket_handlers[callback_id]
            for task, handler in handlers:
                if task.done():
                    logger.debug("Removing websocket handler for id: " + callback_id)
                    handlers.remove((task, handler))

        to_remove_callback_id = []

        # Search for callback_id with no handlers, and delete them
        for callback_id in websocket_handlers:
            if len(websocket_handlers[callback_id]) == 0:
                to_remove_callback_id.append(callback_id)

        for callback_id in to_remove_callback_id:
            del websocket_handlers[callback_id]
        yield from asyncio.sleep(30)


@asyncio.coroutine
def send(callback_id, message):
    """ Send the message to the websocket handlers linked to a callback_id

        Parameters:
        - callback_id: :str: id
        - message: :str: message to send

        Returns:
        - None
    """
    global websocket_handlers

    if callback_id in websocket_handlers:
        handlers = websocket_handlers[callback_id]

        for task, handler in handlers:
            # (cleanup) if task of websocket is closed, that means websocket
            # closed. no need to send events to that closed websocket
            if task.done():
                handlers.remove((task, handler))
            else:
                yield from handler.send_str(message)


@asyncio.coroutine
def close(callback_id):
    """ Delete all the websocket handler information for a callback_id

        Parameters:
        - callback_id: :str: id

        Returns:
        - None
    """
    global websocket_handlers

    del websocket_handlers[callback_id]
