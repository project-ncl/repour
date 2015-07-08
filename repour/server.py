import asyncio
import collections
import json
import logging

import aiohttp
from aiohttp import web
import voluptuous

from . import exception
from . import pull
from . import repo
from . import validation

logger = logging.getLogger(__name__)

#
# Handlers
#

@asyncio.coroutine
def show_id(request):
    return web.Response(
        content_type="text/plain",
        text="Repour",
    )

@asyncio.coroutine
def pull_source(request):
    pullspec = yield from request.json()
    try:
        validation.pull(pullspec)
    except voluptuous.MultipleInvalid as x:
        return web.Response(
            status=400,
            content_type="application/json",
            text=json.dumps(
                obj=[e.__dict__ for e in x.errors],
                ensure_ascii=False,
            ),
        )

    try:
        internal = yield from pull.pull(pullspec, request.app["repo_provider"])
    except exception.DescribedError as e:
        error = {k: v for k, v in e.__dict__.items() if not k.startsWith("_")}
        error["error_type"] = e.__class__.__name__
        return web.Response(
            status=400,
            content_type="application/json",
            text=json.dumps(
                obj=error,
                ensure_ascii=False,
            ),
        )

    return web.Response(
        status=200,
        content_type="application/json",
        text=json.dumps(
            obj=internal,
            ensure_ascii=False,
        )
    )

#
# Setup
#

@asyncio.coroutine
def init(loop, bind, repo_provider):
    logger.debug("Running init")
    app = web.Application(loop=loop)

    logger.debug("Adding application resources")
    app["repo_provider"] = repo.provider_types[repo_provider["type"]](repo_provider["url"])

    logger.debug("Setting up handlers")
    app.router.add_route("GET", "/", show_id)
    app.router.add_route("POST", "/pull", pull_source)

    logger.debug("Creating asyncio server")
    srv = yield from loop.create_server(app.make_handler(), bind["address"], bind["port"])
    for socket in srv.sockets:
        logger.info("Server started on socket: {}".format(socket.getsockname()))

def start_server(bind, repo_provider):
    logger.debug("Starting server")
    loop = asyncio.get_event_loop()

    # Monkey patch for Python 3.4.1
    if not hasattr(loop, "create_task"):
        loop.create_task = lambda c: asyncio.async(c, loop=loop)

    loop.run_until_complete(init(
        loop=loop,
        bind=bind,
        repo_provider=repo_provider,
    ))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.debug("KeyboardInterrupt")
    finally:
        logger.info("Stopping tasks")
        tasks = asyncio.Task.all_tasks()
        for task in tasks:
            task.cancel()
        results = loop.run_until_complete(asyncio.gather(*tasks, loop=loop, return_exceptions=True))
        exception_results = [r for r in results if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError)]
        if len(exception_results) > 1:
            raise Exception(exception_results)
        elif len(exception_results) == 1:
            raise exception_results[0]
        loop.close()
