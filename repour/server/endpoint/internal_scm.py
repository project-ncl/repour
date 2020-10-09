import repour
from aiohttp import web
from prometheus_async.aio import time
from prometheus_client import Histogram, Summary

import asyncssh

from ... import exception

REQ_TIME = Summary("internal_scm_req_time", "time spent with internal-scm endpoint")
REQ_HISTOGRAM_TIME = Histogram("internal_scm_histogram", "Histogram for internal-scm endpoint")

logger = logging.getLogger(__name__)

@time(REQ_TIME)
@time(REQ_HISTOGRAM_TIME)
async def internal_scm(spec, repo_provider):
    """
    spec is looks like validation.internal_scm

    Output is:
    => success: {"status": "SUCCESS"}
    => failure: {"status": "FAILURE", "exit_status": <exit status:int>, "log": "<log: str>"}
    """

    config = await config.get_configuration()

    async with asyncssh.connect(config.get("gerrit_hostname"), username = config.get("gerrit_username"), known_hosts=None) as conn:

        command = gerrit_command(spec.get('project'), spec.get('parent_project'), spec.get('owner_groups'), spec.get('description'))
        logger.info("Command to run: {}", command")
        result = await conn.run(command, check=True)
        exit_status = result.exit_status

        if exit_status == 0:
            return {'status': 'SUCCESS'}
        else:
            return {'status': 'FAILURE', 'exit_status': exit_status, 'log': result.stderr}


def build_gerrit_command(project, parent_project, owner_groups, description):
    command = "gerrit create-project '{}.git'".format(project)

    if parent_project:
        command += " -p {}".format(parent_project)

    if description:
        command +=  " -d {}".format(description)

    for owner in owner_groups:
        command += "-o {}".format(owner)

    return command
