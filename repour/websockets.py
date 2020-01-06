# flake8: noqa
import asyncio
import logging
import os

from repour.lib.logs.file_callback_log import get_callback_log_path

# Period to re-read file to see if change happened
PERIOD = 0.3

logger = logging.getLogger(__name__)

# Global object with key: callback_id and
# value (asyncio_task, websocket_handler)
websocket_handlers = {}
websocket_taillog_workers = {}


async def register(callback_id, task, websocket_handler):
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
    global websocket_taillog_workers

    if callback_id not in websocket_handlers:
        websocket_handlers[callback_id] = [(task, websocket_handler)]
    else:
        websocket_handlers[callback_id].append((task, websocket_handler))

    # create task to tail logs to websocket as new line added to log file
    if callback_id not in websocket_taillog_workers:
        websocket_taillog_workers[callback_id] = asyncio.get_event_loop().create_task(
            setup_tail_job(callback_id)
        )
    else:
        # error handling: check on current task and create new one if task is 'done'
        task = websocket_taillog_workers[callback_id]
        if task is None or task.done():
            websocket_taillog_workers[
                callback_id
            ] = asyncio.get_event_loop().create_task(setup_tail_job(callback_id))


async def setup_tail_job(callback_id):
    """
    Starts by going to end of logfile of callback_id, then sending any new lines written to the logfile to the websocket clients
    Infinite loop, so at some point that task has to be explicitly deleted.

    If logfile doesn't exist, just stop
    """

    path = get_callback_log_path(callback_id)

    if os.path.exists(path):
        with open(path) as f:
            # seek to end of file initially to simulate 'tail'
            next_seek = f.seek(0, 2)

        while True:

            line, next_seek = await readline(path, next_seek)
            await send(callback_id, line)


async def readline(path, next_seek):
    """
    Helper function to only return when there is a new line written to the file. Otherwise it sleeps for PERIOD seconds

    Re-open the file everytime to avoid syncing / caching issues with shared storage
    """
    while True:
        with open(path, "r") as f:

            f.seek(next_seek)
            data = f.readline()

            if data:
                return data, f.tell()

        await asyncio.sleep(PERIOD)


async def periodic_cleanup():
    """ Cleanup the websocket_handlers datastructure by removing closed
        websocket handlers and callback_ids with empty websocket list

        It runs every 30 seconds. It needs to be launched inside its own task

        Parameters:
        - None

        Returns:
        - None
    """
    global websocket_handlers
    global websocket_taillog_workers

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
            logger.info("Removing websocket information for task_id: " + callback_id)
            del websocket_handlers[callback_id]

            if callback_id in websocket_taillog_workers:

                task = websocket_taillog_workers[callback_id]

                # cancel the task to tail first
                if task is not None:
                    task.cancel()

                # then delete the key also
                del websocket_taillog_workers[callback_id]

        await asyncio.sleep(30)


async def send(callback_id, message):
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
                await handler.send_str(message)


async def close(callback_id):
    """ Delete all the websocket handler information for a callback_id

        Parameters:
        - callback_id: :str: id

        Returns:
        - None
    """
    global websocket_handlers
    global websocket_taillog_workers

    del websocket_handlers[callback_id]

    if callback_id in websocket_taillog_workers:

        task = websocket_taillog_workers[callback_id]

        if task is not None:
            task.cancel()

        del websocket_taillog_workers[callback_id]
