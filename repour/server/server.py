# flake8: noqa
import asyncio
import logging
import os

import prometheus_async.aio as aio
from aiohttp import web
from prometheus_client.bridge.graphite import GraphiteBridge

from repour import clone, repo, websockets
from repour.adjust import adjust
from repour.auth import auth
from repour.config import config
from repour.server.endpoint import (
    cancel,
    endpoint,
    external_to_internal,
    info,
    validation,
    ws,
    internal_scm,
)

logger = logging.getLogger(__name__)

#
# Setup
#

shutdown_callbacks = []


async def init(loop, bind, repo_provider, repour_url, adjust_provider):
    logger.debug("Running init")
    c = await config.get_configuration()

    auth_provider = c.get("auth", {}).get("provider", None)
    logger.info("Using auth provider '" + str(auth_provider) + "'.")

    app = web.Application(
        loop=loop, middlewares=[auth.providers[auth_provider]] if auth_provider else {}
    )

    logger.debug("Adding application resources")
    app["repo_provider"] = repo.provider_types[repo_provider["type"]](
        **repo_provider["params"]
    )

    external_to_internal_source = endpoint.validated_json_endpoint(
        shutdown_callbacks,
        validation.external_to_internal,
        external_to_internal.translate,
        repour_url,
    )

    adjust_source = endpoint.validated_json_endpoint(
        shutdown_callbacks, validation.adjust_modeb, adjust.adjust, repour_url
    )

    internal_scm_source = endpoint.validated_json_endpoint(
        shutdown_callbacks,
        validation.internal_scm,
        internal_scm.internal_scm,
        repour_url,
    )

    logger.debug("Setting up handlers")
    app.router.add_route("GET", "/", info.handle_request)
    app.router.add_route(
        "POST", "/git-external-to-internal", external_to_internal_source
    )

    app.router.add_route(
        "POST",
        "/clone",
        endpoint.validated_json_endpoint(
            shutdown_callbacks, validation.clone, clone.clone, repour_url
        ),
    )

    app.router.add_route("POST", "/adjust", adjust_source)
    app.router.add_route("POST", "/internal-scm", internal_scm_source)
    app.router.add_route("POST", "/cancel/{task_id}", cancel.handle_cancel)
    app.router.add_route("GET", "/callback/{callback_id}", ws.handle_socket)
    app.router.add_route("GET", "/metrics", aio.web.server_stats)

    await setup_graphite_exporter()
    # used for distributed cancel operation
    asyncio.get_event_loop().create_task(cancel.start_cancel_loop())

    logger.debug("Creating asyncio server")
    srv = await loop.create_server(
        app.make_handler(access_log=None), bind["address"], bind["port"]
    )
    for socket in srv.sockets:
        logger.info("Server started on socket: {}".format(socket.getsockname()))


def start_server(bind, repo_provider, repour_url, adjust_provider):
    logger.debug("Starting server")
    loop = asyncio.get_event_loop()

    loop.run_until_complete(
        init(
            loop=loop,
            bind=bind,
            repo_provider=repo_provider,
            repour_url=repour_url,
            adjust_provider=adjust_provider,
        )
    )

    loop.create_task(websockets.periodic_cleanup())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.debug("KeyboardInterrupt")
    finally:
        logger.info("Stopping tasks and shutting down")
        tasks = asyncio.Task.all_tasks()
        for task in tasks:
            task.cancel()
        results = loop.run_until_complete(
            asyncio.gather(*tasks, loop=loop, return_exceptions=True)
        )
        for shutdown_callback in shutdown_callbacks:
            shutdown_callback()
        exception_results = [
            r
            for r in results
            if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError)
        ]
        if len(exception_results) > 1:
            raise Exception(exception_results)
        elif len(exception_results) == 1:
            raise exception_results[0]
        loop.close()


async def setup_graphite_exporter():

    graphite_server = os.environ.get("GRAPHITE_SERVER", None)
    graphite_key = os.environ.get("GRAPHITE_KEY", None)
    graphite_port = os.environ.get("GRAPHITE_PORT", 2003)

    if graphite_server is None or graphite_key is None:
        logger.warn(
            "Graphite server ("
            + str(graphite_server)
            + ") or Graphite key ("
            + str(graphite_key)
            + ") is not defined. Not setting up Monitoring graphite server!"
        )
        return

    logger.info(
        "Monitoring graphite server setup! Reporting to server: "
        + graphite_server
        + ":"
        + str(graphite_port)
        + " with prefix: "
        + str(graphite_key)
    )

    gb = GraphiteBridge((graphite_server, graphite_port))
    gb.start(60.0, prefix=graphite_key)
