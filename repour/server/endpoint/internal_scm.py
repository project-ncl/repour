import logging

from prometheus_async.aio import time
from prometheus_client import Histogram, Summary

from repour.config import config
from repour.server.endpoint import (
    internal_scm_gerrit,
    internal_scm_gitlab,
)

REQ_TIME = Summary("internal_scm_req_time", "time spent with internal-scm endpoint")
REQ_HISTOGRAM_TIME = Histogram(
    "internal_scm_histogram", "Histogram for internal-scm endpoint"
)

logger = logging.getLogger(__name__)


@time(REQ_TIME)
@time(REQ_HISTOGRAM_TIME)
async def internal_scm(spec, repo_provider):
    """
    spec is looks like validation.internal_scm

    Output is:
    => success: {"status": "SUCCESS_CREATED", "readonly_url": "..", "readwrite_url": ".."} if project created
    => success: {"status": "SUCCESS_ALREADY_EXISTS", "readonly_url": "..", "readwrite_url": ".."} if project created
    => failure: {"status": "FAILURE", "exit_status": <exit status:int>, "command_log": "<log: str>"}
    """

    configuration = await config.get_configuration()
    git_backend = configuration.get("git_backend")

    logger.debug("Git backend is " + git_backend)

    if git_backend == "gitlab":
        return await internal_scm_gitlab.internal_scm_gitlab(spec, repo_provider)
    elif git_backend == "gerrit":
        return await internal_scm_gerrit.internal_scm_gerrit(spec, repo_provider)
    else:
        raise Exception("Unknown git server type: " + git_backend)
