# flake8: noqa
import asyncio
import base64
import concurrent.futures as cfutures
import hashlib
import json
import logging
import os
import sys
import traceback

import aiohttp
import asyncio
import voluptuous
from aiohttp import web
from prometheus_async.aio import time
from prometheus_client import Counter, Histogram, Summary

from repour import exception
from repour.config import config
from repour.lib.io import file_utils
from repour.lib.logs import log_util
from repour.server.endpoint import validation
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)


ERROR_VALIDATION_JSON_COUNTER = Counter(
    "error_validation_json_counter",
    "User sent bad JSON requests that failed validation",
)
ERROR_RESPONSE_400_COUNTER = Counter(
    "error_response_400_counter", "App returned 400 status"
)
ERROR_RESPONSE_500_COUNTER = Counter(
    "error_response_500_counter", "App returned 500 status"
)
ERROR_CALLBACK_COUNTER = Counter(
    "error_callback_counter", "Errors calling callback url"
)

REQ_TIME = Summary("callback_time", "time spent with calling callback")
REQ_HISTOGRAM_TIME = Histogram("callback_histogram", "Histogram for calling callback")


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
    """

    Note: Do not try to create one log line per error. This messes up with splunk logging that shows everything per line
    """
    text = traceback.format_exc()
    logger.error(text)


def validated_json_endpoint(shutdown_callbacks, validator, coro, repour_url):
    client_session = aiohttp.ClientSession()  # pylint: disable=no-member
    shutdown_callbacks.append(client_session.close)

    async def handler(request):
        c = await config.get_configuration()

        log_context = request.headers.get("LOG-CONTEXT", "").strip()
        if log_context == "":
            log_context = create_log_context_id()

        log_user_id = request.headers.get("log-user-id", "").strip()
        log_request_context = request.headers.get("log-request-context", "").strip()
        log_process_context = request.headers.get("log-process-context", "").strip()
        log_expires = request.headers.get("log-expires", "").strip()
        log_tmp = request.headers.get("log-tmp", "").strip()
        log_process_context_variant = request.headers.get(
            "process-context-variant", ""
        ).strip()
        trace_id = request.headers.get("trace-id", "").strip()
        span_id = request.headers.get("span-id", "").strip()
        traceparent = request.headers.get("traceparent", "").strip()
        tracestate = request.headers.get("tracestate", "").strip()
        logger.info(">> traceparent: " + traceparent)
        logger.info(">> tracestate: " + tracestate)
        # Some implementations use parent-id instead of span-id
        if span_id == "":
            span_id = request.headers.get("parent-id", "").strip()

        callback_id = create_callback_id()

        asyncio.current_task().log_context = log_context

        # required for bifrost for streaming logs
        asyncio.current_task().loggerName = "org.jboss.pnc._userlog_.alignment-log"

        log_util.add_update_mdc_key_value_in_task("userId", log_user_id)
        log_util.add_update_mdc_key_value_in_task("requestContext", log_request_context)
        log_util.add_update_mdc_key_value_in_task("processContext", log_process_context)
        log_util.add_update_mdc_key_value_in_task("expires", log_expires)
        log_util.add_update_mdc_key_value_in_task("tmp", log_tmp)
        log_util.add_update_mdc_key_value_in_task(
            "processContextVariant", log_process_context_variant
        )
        log_util.add_update_mdc_key_value_in_task("trace_id", trace_id)
        log_util.add_update_mdc_key_value_in_task("span_id", span_id)
        log_util.add_update_mdc_key_value_in_task("traceparent", traceparent)

        asyncio.current_task().callback_id = callback_id

        try:
            spec = await request.json()
        except ValueError:
            logger.error(
                "Rejected {method} {path}: body is not parsable as json".format(
                    method=request.method, path=request.path
                )
            )

            rejected_data = await request.text()

            ERROR_VALIDATION_JSON_COUNTER.inc()
            logger.error("Request data: {data}".format(data=rejected_data))

            return web.Response(
                status=400,
                content_type="application/json",
                text=json.dumps(
                    obj=[
                        {
                            "error_message": "expected json",
                            "error_type": "json parsability",
                            "path": [],
                        }
                    ],
                    ensure_ascii=False,
                ),
            )
        try:
            validator(spec)
        except voluptuous.MultipleInvalid as x:

            logger.error(
                "Rejected {method} {path}: body failed input validation".format(
                    method=request.method, path=request.path
                )
            )

            ERROR_VALIDATION_JSON_COUNTER.inc()

            logger.error("Request data: {data}".format(data=spec))

            return web.Response(
                status=400,
                content_type="application/json",
                text=json.dumps(obj=[e.__dict__ for e in x.errors], ensure_ascii=False),
            )
        logger.info(
            "Accepted {method} {path}: {params}".format(
                method=request.method, path=request.path, params=spec
            )
        )

        try:
            validation.callback(spec)
        except voluptuous.MultipleInvalid as x:
            callback_mode = False
        else:
            callback_mode = True

        # Set the task_id if provided in the request
        task_id = spec.get("taskId", None)
        if task_id:
            asyncio.current_task().task_id = task_id

        async def do_call():
            try:
                ret = await coro(spec, **request.app)
            except cfutures.CancelledError as e:
                # do nothing else
                logger.info("Cancellation request received")
                raise e

            except exception.DescribedError as e:
                status = 400
                traceback_id, obj = described_error_to_obj(e)
                ERROR_RESPONSE_400_COUNTER.inc()
                logger.error(
                    "Failed ({e.__class__.__name__}), traceback hash: {traceback_id}".format(
                        **locals()
                    )
                )
                log_traceback_multi_line()
            except Exception as e:
                status = 500
                traceback_id, obj = exception_to_obj(e)
                ERROR_RESPONSE_500_COUNTER.inc()
                logger.error(
                    "Internal failure ({e.__class__.__name__}), traceback hash: {traceback_id}".format(
                        **locals()
                    )
                )
                log_traceback_multi_line()
            else:
                status = 200
                obj = ret
                logger.info("Completed ok")

            return status, obj

        if callback_mode:

            async def do_callback(callback_spec):
                status, obj = await do_call()

                obj["callback"] = {"status": status, "id": callback_id}

                logger.info("Callback data: {}".format(obj))

                @time(REQ_TIME)
                @time(REQ_HISTOGRAM_TIME)
                async def send_result():
                    try:
                        # TODO refactor this into auth.py, we cannot use middleware for callbacks
                        headers = {}

                        current_task = asyncio.current_task()

                        auth_provider = c.get("auth", {}).get("provider", None)
                        if auth_provider == "oauth2_jwt" and request.headers.get(
                            "Authorization", None
                        ):
                            auth_header = {
                                "Authorization": request.headers["Authorization"]
                            }
                            logger.debug(
                                "Authorization enabled, adding header to callback: "
                                + str(auth_header)
                            )
                            headers.update(auth_header)

                        context_headers = {
                            "log-user-id": current_task.mdc["userId"],
                            "log-request-context": current_task.mdc["requestContext"],
                            "log-process-context": current_task.mdc["processContext"],
                            "log-expires": current_task.mdc["expires"],
                            "log_tmp": current_task.mdc["tmp"],
                            "process-context-variant": current_task.mdc[
                                "processContextVariant"
                            ],
                            "trace-id": current_task.mdc["trace_id"],
                            "span-id": current_task.mdc["span_id"],
                            "traceparent": current_task.mdc["traceparent"],
                        }

                        headers.update(context_headers)
                        headers.update({"Content-Type": "application/json"})

                        # callback url is either from key 'url' or 'uri'. The latter is used in the pnc-api Request object
                        resp = await client_session.request(
                            callback_spec.get("method", "POST"),
                            callback_spec.get("url", callback_spec.get("uri")),
                            headers=headers,
                            data=json.dumps(obj=obj, ensure_ascii=False).encode(
                                "utf-8"
                            ),
                        )
                    except Exception as e:
                        ERROR_CALLBACK_COUNTER.inc()
                        logger.error(
                            "Unable to send result of callback, exception {ename}, attempt {backoff}/{max_attempts}".format(
                                ename=e.__class__.__name__,
                                backoff=backoff,
                                max_attempts=max_attempts,
                            )
                        )
                        logger.error(e)
                        resp = None
                    return resp

                backoff = 1
                max_attempts = 9
                resp = await send_result()

                while resp is None or resp.status // 100 != 2:
                    if resp is not None:
                        logger.info(
                            "Unable to send result of callback, status {resp.status}, attempt {backoff}/{max_attempts}".format(
                                **locals()
                            )
                        )

                    sleep_period = 2**backoff
                    logger.debug("Sleeping for {sleep_period}".format(**locals()))
                    await asyncio.sleep(sleep_period)

                    backoff += 1

                    if backoff > max_attempts:
                        logger.error(
                            "Giving up on callback after {max_attempts} attempts".format(
                                **locals()
                            )
                        )
                        break

                    resp = await send_result()

                if backoff <= max_attempts:
                    logger.info("Callback result sent successfully")

            logger.info(
                "Creating callback task {callback_id}, returning ID now".format(
                    **locals()
                )
            )

            # trying
            ctx = TraceContextTextMapPropagator().extract(
                carrier={"traceparent": traceparent}
            )
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(request.path, ctx) as span:

                callback_task = request.app.loop.create_task(
                    do_callback(spec["callback"])
                )
                callback_task.log_context = log_context
                callback_task.loggerName = asyncio.current_task().loggerName
                callback_task.mdc = asyncio.current_task().mdc
                callback_task.callback_id = callback_id
                # Set the task_id if provided in the request
                task_id = spec.get("taskId", None)
                if task_id:
                    callback_task.task_id = task_id

                status = 202
                obj = {
                    "callback": {
                        "id": callback_id,
                        "websocket": "ws://" + repour_url + "/callback/" + callback_id,
                    }
                }

        else:
            status, obj = await do_call()

        response = web.Response(
            status=status,
            content_type="application/json",
            text=json.dumps(obj=obj, ensure_ascii=False),
        )
        return response

    return handler
