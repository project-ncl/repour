import logging

import asyncssh

from repour.config import config

logger = logging.getLogger(__name__)


async def internal_scm_gerrit(spec, repo_provider):
    """
    spec is looks like validation.internal_scm

    Output is:
    => success: {"status": "SUCCESS_CREATED", "readonly_url": "..", "readwrite_url": ".."} if project created
    => success: {"status": "SUCCESS_ALREADY_EXISTS", "readonly_url": "..", "readwrite_url": ".."} if project created
    => failure: {"status": "FAILURE", "exit_status": <exit status:int>, "command_log": "<log: str>"}
    """

    configuration = await config.get_configuration()
    configuration = configuration.get("gerrit")

    readonly_url = configuration.get("read_only_template")
    readwrite_url = configuration.get("read_write_template")

    command = build_gerrit_command(
        spec.get("project"),
        spec.get("parent_project"),
        spec.get("owner_groups"),
        spec.get("description"),
    )

    logger.info("Command to run: " + command)

    async with asyncssh.connect(
        configuration.get("hostname"),
        username=configuration.get("username"),
        known_hosts=None,
    ) as conn:
        result = await conn.run(command, check=False)
        exit_status = result.exit_status

        if exit_status == 0:
            return {
                "status": "SUCCESS_CREATED",
                "readonly_url": readonly_url.format(REPO_NAME=spec.get("project")),
                "readwrite_url": readwrite_url.format(REPO_NAME=spec.get("project")),
            }
        elif exit_status == 1 and "Project already exists" in result.stderr:
            return {
                "status": "SUCCESS_ALREADY_EXISTS",
                "readonly_url": readonly_url.format(REPO_NAME=spec.get("project")),
                "readwrite_url": readwrite_url.format(REPO_NAME=spec.get("project")),
            }
        else:
            raise Exception("Creation failed! Command log: " + result.stderr)


def build_gerrit_command(project, parent_project, owner_groups, description):
    command = "gerrit create-project '{}.git'".format(project)

    if parent_project:
        command += " -p '{}'".format(parent_project)

    if description:
        command += " -d '{}'".format(description)

    for owner in owner_groups:
        command += " -o '{}'".format(owner)

    return command
