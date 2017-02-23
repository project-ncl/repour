import asyncio
import logging

from aiohttp import web

from .endpoint import cancel
from .endpoint import is_branch
from .endpoint import endpoint
from ..adjust import adjust
from .. import clone
from .. import pull
from .. import repo
from .endpoint import validation
from ..auth import auth
from ..config import config

logger = logging.getLogger(__name__)

#
# Setup
#

shutdown_callbacks = []


@asyncio.coroutine
def init(loop, bind, repo_provider, adjust_provider):
    logger.debug("Running init")
    c = yield from config.get_configuration()

    auth_provider = c.get('auth', {}).get('provider', None)
    logger.info("Using auth provider '" + str(auth_provider) + "'.")

    app = web.Application(loop=loop, middlewares=[auth.providers[auth_provider]] if auth_provider else {})

    logger.debug("Adding application resources")
    app["repo_provider"] = repo.provider_types[repo_provider["type"]](**repo_provider["params"])

    if repo_provider["type"] == "modeb":
        logger.warn("Mode B selected, guarantees rescinded")
        pull_source = endpoint.validated_json_endpoint(shutdown_callbacks, validation.pull_modeb, pull.pull)
        adjust_source = endpoint.validated_json_endpoint(shutdown_callbacks, validation.adjust_modeb, adjust.adjust)
    else:
        pull_source = endpoint.validated_json_endpoint(shutdown_callbacks, validation.pull, pull.pull)
        adjust_source = endpoint.validated_json_endpoint(shutdown_callbacks, validation.adjust, adjust.adjust)

    logger.debug("Setting up handlers")
    app.router.add_route("POST", "/pull", pull_source)
    app.router.add_route("POST", "/adjust", adjust_source)
    app.router.add_route("POST", "/clone", endpoint.validated_json_endpoint(shutdown_callbacks, validation.clone, clone.clone))
    app.router.add_route("POST", "/cancel", cancel.handle_cancel)
    app.router.add_route("POST", "/is-branch", is_branch.is_branch)

    logger.debug("Creating asyncio server")
    srv = yield from loop.create_server(app.make_handler(), bind["address"], bind["port"])
    for socket in srv.sockets:
        logger.info("Server started on socket: {}".format(socket.getsockname()))


def start_server(bind, repo_provider, adjust_provider):
    logger.debug("Starting server")
    loop = asyncio.get_event_loop()

    # Monkey patch for Python 3.4.1
    if not hasattr(loop, "create_task"):
        loop.create_task = lambda c: asyncio.async(c, loop=loop)

    loop.run_until_complete(init(
        loop=loop,
        bind=bind,
        repo_provider=repo_provider,
        adjust_provider=adjust_provider,
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
        for shutdown_callback in shutdown_callbacks:
            shutdown_callback()
        exception_results = [r for r in results if
                             isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError)]
        if len(exception_results) > 1:
            raise Exception(exception_results)
        elif len(exception_results) == 1:
            raise exception_results[0]
        loop.close()
