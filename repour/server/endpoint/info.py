# flake8: noqa
import os
import sys

import json
import logging
import repour
from aiohttp import web
from prometheus_async.aio import time
from prometheus_client import Histogram, Summary

from repour import exception
from repour.lib.scm import git

REQ_TIME = Summary("info_req_time", "time spent with info endpoint")
REQ_HISTOGRAM_TIME = Histogram("info_req_histogram", "Histogram for info endpoint")

logger = logging.getLogger(__name__)

GIT_SHA = None


@time(REQ_TIME)
@time(REQ_HISTOGRAM_TIME)
async def handle_request(request):
    global GIT_SHA

    version = repour.__version__
    path_name = os.path.dirname(sys.argv[0])

    # cache git sha output since the request can be slow
    if GIT_SHA is None:
        try:
            logger.info("Getting the SHA for repour")
            GIT_SHA = await git.rev_parse(path_name)
        except exception.CommandError:
            GIT_SHA = "Unknown"

    html_text = """
    <h1>Repour Information</h1>
    <ul>
        <li><strong>Repour Version</strong> {}</li>
        <li><strong>Commit Hash</strong> {}</li>
    </ul>
    """

    html_text = html_text.format(version, GIT_SHA)
    return web.Response(text="" + html_text, content_type="text/html")


@time(REQ_TIME)
@time(REQ_HISTOGRAM_TIME)
async def handle_version(request):
    version = repour.__version__
    path_name = os.path.dirname(sys.argv[0])
    try:
        git_sha = await git.rev_parse(path_name)
    except exception.CommandError:
        git_sha = "Unknown"

    data = {
        "name": "Repour",
        "version": version,
        "commit": git_sha,
        "builtOn": None,
        "components": [],
    }

    # allow CORS
    headers = {"Access-Control-Allow-Origin": "*"}
    return web.Response(
        text="" + json.dumps(data), content_type="application/json", headers=headers
    )
