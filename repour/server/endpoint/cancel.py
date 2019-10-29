import asyncio
import calendar
import json
import logging
import os
import time as python_time

from aiohttp import web
from prometheus_async.aio import time
from prometheus_client import Histogram, Summary
from repour import asutil

REQ_TIME = Summary("cancel_req_time", "time spent with cancel endpoint")
REQ_HISTOGRAM_TIME = Histogram("cancel_req_histogram", "Histogram for cancel endpoint")

PERIOD_CANCEL_LOOP_SLEEP = 0.5

SHARED_PATH_PREFOLDER = os.environ.get("SHARED_FOLDER", "/tmp")
CANCEL_PATH = os.path.join(SHARED_PATH_PREFOLDER, "cancel-notify")

logger = logging.getLogger(__name__)


@time(REQ_TIME)
@time(REQ_HISTOGRAM_TIME)
async def handle_cancel(request):

    task_id_to_cancel = request.match_info["task_id"]
    logger.info("Cancel request obtained: " + str(task_id_to_cancel))

    if not task_id_to_cancel:
        response = await bad_response("Task id is not provided")
        return response

    cancelled_tasks = False
    task_id_dict = get_task_id_dict()

    if task_id_to_cancel in task_id_dict:
        task_id_dict[task_id_to_cancel].cancel()
        cancelled_tasks = True
    else:
        cancelled_tasks = await check_if_other_repour_replicas_cancelled(
            task_id_to_cancel
        )

    if cancelled_tasks:
        response = await success_response(
            "Tasks with task_id: " + str(task_id_to_cancel) + " cancelled"
        )
        return response
    else:
        # if we are here, the task id wasn't found
        response = await bad_response(
            "task id " + str(task_id_to_cancel) + " not found!"
        )
        return response


async def bad_response(error_message):
    logger.warn(error_message)
    response = web.Response(
        status=400,
        content_type="application/json",
        text=json.dumps(obj=[{"error_message": error_message}], ensure_ascii=False),
    )
    return response


async def success_response(message):

    logger.info(message)

    response = web.Response(
        status=200,
        content_type="application/json",
        text=json.dumps(obj=[{"message": message}], ensure_ascii=False),
    )
    return response


# The start_cancel_loop and the check_if_other_repour_replicas_cancelled work hand in hand
# Those stuff are done to be able to run repour with multiple replicas
#
# When a request to cancel a task comes in, we first check if the task is present in the
# repour server which got the request.
#
# If yes -> cancel that task and report back to the client
#
# If no ->
# - Create an indicator file in a shared location to indicate that we want to cancel a task
# - Verify every PERIOD_CANCEL_LOOP_SLEEP seconds, for up to 10 times, if the indicator file got deleted
# - if yes -> the cancel was successful
# - if no -> cancel was unsuccessful. Delete the indicator file and tell the caller the cancel operation was unsuccessful

# - that indicator file is seen by other repour replicas (via the shared location) in the 'start_cancel_loop'
# - the other repour replicas check their event loop, and if they found and cancelled the task, they delete the indicator file
#
# The 'start_cancel_loop' runs every PERIOD_CANCEL_LOOP_SLEEP seconds to check
async def start_cancel_loop():

    if not os.path.exists(CANCEL_PATH):
        os.makedirs(CANCEL_PATH)

    while True:

        cancel_files = os.listdir(CANCEL_PATH)

        if len(cancel_files) > 0:
            # if we're here, there are cancel tasks to process
            task_id_dict = get_task_id_dict()

            for filename in cancel_files:
                # format is <task_id>.cancel
                if filename.endswith(".cancel"):
                    task_id_to_cancel = filename.replace(".cancel", "")

                    if task_id_to_cancel in task_id_dict:

                        logger.info(
                            "From cancel loop: cancelling task: " + task_id_to_cancel
                        )

                        task_id_dict[task_id_to_cancel].cancel()
                        os.remove(os.path.join(CANCEL_PATH, filename))

        await remove_old_cancel_indicator_files()
        await asyncio.sleep(PERIOD_CANCEL_LOOP_SLEEP)


async def check_if_other_repour_replicas_cancelled(task_id):

    cancel_indicator_filename = os.path.join(CANCEL_PATH, task_id + ".cancel")

    if not os.path.exists(cancel_indicator_filename):
        f = open(cancel_indicator_filename, "w")
        f.close()

    for _ in range(10):

        # task id was cancelled in another repour replica
        if not os.path.exists(cancel_indicator_filename):
            return True

        await asyncio.sleep(PERIOD_CANCEL_LOOP_SLEEP)

    # if we're here, no other replicas cancelled the task_id, abandoning
    logger.warn("No other repour replicas cancelled task: " + task_id + ". Giving up!")
    os.remove(cancel_indicator_filename)
    return False


async def remove_old_cancel_indicator_files():
    """ In case there are old cancel indicator files that are present and wasn't cleaned up properly, delete them

    Old files defined as having an age greater than 1 hour
    """
    for filename in os.listdir(CANCEL_PATH):

        path = os.path.join(CANCEL_PATH, filename)

        epoch_filename = int(os.stat(path).st_ctime)
        current_epoch = calendar.timegm(python_time.gmtime())

        if current_epoch - epoch_filename > 3600:
            logger.warn("Removing old cancel taskid file indicator: " + path)
            asutil.safe_remove_file(path)


def get_task_id_dict():

    all_tasks = asyncio.Task.all_tasks()
    task_id_dict = {}

    for task in all_tasks:
        task_id_of_task = getattr(task, "task_id", None)

        if task_id_of_task is not None:
            task_id_dict[task_id_of_task] = task

    return task_id_dict
