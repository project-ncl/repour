import os
import repour
import sys
from aiohttp import web
from ...scm import git_provider
from ... import exception

from prometheus_client import Summary
from prometheus_client import Histogram
from prometheus_async.aio import time

REQ_TIME = Summary("info_req_time", "time spent with info endpoint")
REQ_HISTOGRAM_TIME = Histogram("info_req_histogram", "Histogram for info endpoint")

@time(REQ_TIME)
@time(REQ_HISTOGRAM_TIME)
async def handle_request(request):
    version = repour.__version__
    path_name = os.path.dirname(sys.argv[0])
    try:
        git_sha = await git_provider.git_provider()["rev_parse"](path_name)
    except exception.CommandError:
        git_sha = "Unknown"

    html_text = """
    <h1>Repour Information</h1>
    <ul>
        <li><strong>Repour Version</strong> {}</li>
        <li><strong>Commit Hash</strong> {}</li>
    </ul>
    """

    html_text = html_text.format(version, git_sha)
    return web.Response(text='' + html_text, content_type="text/html")


