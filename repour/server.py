import asyncio
import base64
import hashlib
import json
import logging
import os
import traceback

import aiohttp
import voluptuous
from aiohttp import web

from . import adjust
from .auth import auth
from . import clone
from .config import config
from . import exception
from . import pull
from . import repo
from . import validation

logger = logging.getLogger(__name__)


def create_log_context_id():
    return "repour-" + base64.b32encode(os.urandom(20)).decode("ascii").lower()


def create_callback_id():
    return base64.b32encode(os.urandom(30)).decode("ascii")


def create_traceback_id():
    tb = traceback.format_exc()
    h = hashlib.md5()
    h.update(tb.encode("utf-8"))
    return h.hexdigest()


def described_error_to_obj(exception):
    traceback_id = create_traceback_id()
    error = {k: v for k, v in exception.__dict__.items() if not k.startswith("_")}
    error["error_type"] = exception.__class__.__name__
    error["error_traceback"] = traceback_id
    return (traceback_id, error)


def exception_to_obj(exception):
    traceback_id = create_traceback_id()
    error = {
        "error_type": exception.__class__.__name__,
        "error_traceback": traceback_id,
    }
    return (traceback_id, error)


def log_traceback_multi_line():
    text = traceback.format_exc()
    for line in text.split("\n"):
        if line != "":
            logger.error(line)


shutdown_callbacks = []


def _validated_json_endpoint(validator, coro):
    client_session = aiohttp.ClientSession()  # pylint: disable=no-member
    shutdown_callbacks.append(client_session.close)

    @asyncio.coroutine
    def handler(request):
        c = yield from config.get_configuration()

        log_context = request.headers.get("LOG-CONTEXT", "").strip()
        if log_context == "":
            log_context = create_log_context_id()
        asyncio.Task.current_task().log_context = log_context

        try:
            spec = yield from request.json()
        except ValueError:
            logger.error("Rejected {method} {path}: body is not parsable as json".format(
                method=request.method,
                path=request.path,
            ))
            return web.Response(
                status=400,
                content_type="application/json",
                text=json.dumps(
                    obj=[{
                        "error_message": "expected json",
                        "error_type": "json parsability",
                        "path": [],
                    }],
                    ensure_ascii=False,
                ),
            )
        try:
            validator(spec)
        except voluptuous.MultipleInvalid as x:
            logger.error("Rejected {method} {path}: body failed input validation".format(
                method=request.method,
                path=request.path,
            ))
            return web.Response(
                status=400,
                content_type="application/json",
                text=json.dumps(
                    obj=[e.__dict__ for e in x.errors],
                    ensure_ascii=False,
                ),
            )
        logger.info("Accepted {method} {path}: {params}".format(
            method=request.method,
            path=request.path,
            params=spec,
        ))

        try:
            validation.callback(spec)
        except voluptuous.MultipleInvalid as x:
            callback_mode = False
        else:
            callback_mode = True

        @asyncio.coroutine
        def do_call():
            try:
                ret = yield from coro(spec, **request.app)
            except exception.DescribedError as e:
                status = 400
                traceback_id, obj = described_error_to_obj(e)
                logger.error("Failed ({e.__class__.__name__}), traceback hash: {traceback_id}".format(**locals()))
                log_traceback_multi_line()
            except Exception as e:
                status = 500
                traceback_id, obj = exception_to_obj(e)
                logger.error(
                    "Internal failure ({e.__class__.__name__}), traceback hash: {traceback_id}".format(**locals()))
                log_traceback_multi_line()
            else:
                status = 200
                obj = ret
                logger.info("Completed ok")
            return status, obj

        if callback_mode:
            callback_id = create_callback_id()

            @asyncio.coroutine
            def do_callback(callback_spec):
                status, obj = yield from do_call()

                obj["callback"] = {
                    "status": status,
                    "id": callback_id,
                }

                @asyncio.coroutine
                def send_result():
                    try:
                        # TODO refactor this into auth.py, we cannot use middleware for callbacks
                        headers = []
                        auth_provider = c.get('auth', {}).get('provider', None)
                        if auth_provider == 'oauth2_jwt' and request.headers.get('Authorization', None):
                            auth_header = {request.headers['Authorization'], 'Authorization'}
                            logger.info('Authorization enabled, adding header to callback: ' + str(auth_header))
                            headers.append(auth_header)

                        resp = yield from client_session.request(
                            callback_spec.get("method", "POST"),
                            callback_spec["url"],
                            headers=headers,
                            data=json.dumps(
                                obj=obj,
                                ensure_ascii=False,
                            ).encode("utf-8")
                        )
                    except Exception as e:
                        logger.info(
                            "Unable to send result of callback, exception {ename}, attempt {backoff}/{max_attempts}".format(
                                ename=e.__class__.__name__,
                                backoff=backoff,
                                max_attempts=max_attempts,
                            ))
                        log_traceback_multi_line()
                        resp = None
                    return resp

                backoff = 0
                max_attempts = 9
                resp = yield from send_result()
                while resp is None or resp.status // 100 != 2:
                    if resp is not None:
                        logger.info(
                            "Unable to send result of callback, status {resp.status}, attempt {backoff}/{max_attempts}".format(
                                **locals()))
                    if backoff > max_attempts:
                        logger.error("Giving up on callback after {max_attempts} attempts".format(**locals()))
                        break
                    sleep_period = 2 ** backoff
                    logger.debug("Sleeping for {sleep_period}".format(**locals()))
                    yield from asyncio.sleep(sleep_period)
                    backoff += 1
                    resp = yield from send_result()
                if backoff <= max_attempts:
                    logger.info("Callback result sent successfully")

            logger.info("Creating callback task {callback_id}, returning ID now".format(**locals()))
            callback_task = request.app.loop.create_task(do_callback(spec["callback"]))
            callback_task.log_context = log_context

            status = 202
            obj = {
                "callback": {
                    "id": callback_id,
                }
            }

        else:
            status, obj = yield from do_call()

        response = web.Response(
            status=status,
            content_type="application/json",
            text=json.dumps(
                obj=obj,
                ensure_ascii=False,
            ),
        )
        return response

    return handler


#
# Handlers
#

@asyncio.coroutine
def show_id(request):
    return web.Response(
        content_type="text/plain",
        text="Repour",
    )


#
# Setup
#

@asyncio.coroutine
def init(loop, bind, repo_provider, adjust_provider):
    logger.debug("Running init")
    c = yield from config.get_configuration()

    auth_provider = c.get('auth', {}).get('provider', None)
    logger.info("Using auth provider '" + str(auth_provider) + "'.")

    app = web.Application(loop=loop, middlewares=[auth.providers[auth_provider]] if auth_provider else {})

    logger.debug("Adding application resources")
    app["repo_provider"] = repo.provider_types[repo_provider["type"]](**repo_provider["params"])
    app["adjust_provider"] = adjust.provider_types[adjust_provider["type"]](**adjust_provider["params"])

    if repo_provider["type"] == "modeb":
        logger.warn("Mode B selected, guarantees rescinded")
        pull_source = _validated_json_endpoint(validation.pull_modeb, pull.pull)
        adjust_source = _validated_json_endpoint(validation.adjust_modeb, adjust.adjust)
    else:
        pull_source = _validated_json_endpoint(validation.pull, pull.pull)
        adjust_source = _validated_json_endpoint(validation.adjust, adjust.adjust)

    logger.debug("Setting up handlers")
    app.router.add_route("POST", "/pull", pull_source)
    app.router.add_route("POST", "/adjust", adjust_source)
    app.router.add_route("POST", "/clone", _validated_json_endpoint(validation.clone, clone.clone))

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
