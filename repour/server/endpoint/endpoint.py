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

from ... import exception
from . import validation
from ...config import config
from ...logs import file_callback_log

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


def validated_json_endpoint(shutdown_callbacks, validator, coro, repour_url):
    client_session = aiohttp.ClientSession()  # pylint: disable=no-member
    shutdown_callbacks.append(client_session.close)

    @asyncio.coroutine
    def handler(request):
        c = yield from config.get_configuration()

        log_context = request.headers.get("LOG-CONTEXT", "").strip()
        if log_context == "":
            log_context = create_log_context_id()

        callback_id = create_callback_id()

        asyncio.Task.current_task().log_context = log_context
        asyncio.Task.current_task().callback_id = callback_id

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

            log_file = file_callback_log.get_callback_log_path(callback_id)
            logs = ""
            if os.path.isfile(log_file):
                with open(log_file, "r") as f:
                    logs = f.read()

            obj["log"] = logs
            return status, obj

        if callback_mode:

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
                        headers = {}
                        auth_provider = c.get('auth', {}).get('provider', None)
                        if auth_provider == 'oauth2_jwt' and request.headers.get('Authorization', None):
                            auth_header = {request.headers['Authorization'], 'Authorization'}
                            logger.info('Authorization enabled, adding header to callback: ' + str(auth_header))
                            headers.update(auth_header)

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
                        logger.error(
                            "Unable to send result of callback, exception {ename}, attempt {backoff}/{max_attempts}".format(
                                ename=e.__class__.__name__,
                                backoff=backoff,
                                max_attempts=max_attempts,
                            ))
                        logger.error(e)
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
            callback_task.callback_id = callback_id

            status = 202
            obj = {
                "callback": {
                    "id": callback_id,
                    "websocket": "ws://" + repour_url + "/callback/" + callback_id
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
