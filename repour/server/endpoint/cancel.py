import asyncio
import json
import logging

from aiohttp import web

from prometheus_client import Summary
from prometheus_client import Histogram
from prometheus_async.aio import time

REQ_TIME = Summary("cancel_req_time", "time spent with cancel endpoint")
REQ_HISTOGRAM_TIME = Histogram("cancel_req_histogram", "Histogram for cancel endpoint")

logger = logging.getLogger(__name__)

@time(REQ_TIME)
@time(REQ_HISTOGRAM_TIME)
async def handle_cancel(request):

    task_id_to_cancel = request.match_info['task_id']
    logger.info("Cancel request obtained: " + str(task_id_to_cancel))

    if not task_id_to_cancel:
        response = await bad_response("Task id is not provided")
        return response

    all_tasks = asyncio.Task.all_tasks()

    cancelled_tasks = False
    for task in all_tasks:
        task_id_of_task = getattr(task, "task_id", None)

        if task_id_of_task == task_id_to_cancel:
            task.cancel()
            cancelled_tasks = True

    if cancelled_tasks:
        response = await success_response("Tasks with task_id: " + str(task_id_to_cancel) + " cancelled")
        return response
    else:
        # if we are here, the task id wasn't found
        response = await bad_response("task id " + str(task_id_to_cancel) + " not found!")
        return response


async def bad_response(error_message):
    logger.warn(error_message)
    response = web.Response(
        status=400,
        content_type="application/json",
        text=json.dumps(
            obj=[{
                "error_message": error_message,
            }],
            ensure_ascii=False,
        ),
    )
    return response


async def success_response(message):

    logger.info(message)

    response = web.Response(
        status=200,
        content_type="application/json",
        text=json.dumps(
            obj=[{
                "message": message,
            }],
            ensure_ascii=False,
        ),
    )
    return response
