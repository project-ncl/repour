import asyncio
import json
import logging

from aiohttp import web

logger = logging.getLogger(__name__)

@asyncio.coroutine
def handle_cancel(request):

    task_id_to_cancel = request.match_info['task_id']
    logger.info("Cancel request obtained: " + str(task_id_to_cancel))

    if not task_id_to_cancel:
        response = yield from bad_response("Task id is not provided")
        return response

    all_tasks = asyncio.Task.all_tasks()

    for task in all_tasks:
        task_id_of_task = getattr(task, "task_id", None)

        if task_id_of_task == task_id_to_cancel:
            task.cancel()
            response = yield from success_response("Task cancelled: " + str(task_id_to_cancel))
            return response
    else:
        # if we are here, the task id wasn't found
        response = yield from bad_response("task id " + str(task_id_to_cancel) + " not found!")
        return response


@asyncio.coroutine
def bad_response(error_message):
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


@asyncio.coroutine
def success_response(message):

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