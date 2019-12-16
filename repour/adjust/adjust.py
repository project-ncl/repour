import asyncio
import logging
import os
import shutil

from prometheus_async.aio import time
from prometheus_client import Histogram, Summary

from .. import asgit, asutil, clone, exception
from ..config import config
from ..scm import git_provider
from . import (
    gradle_provider,
    noop_provider,
    pme_provider,
    process_provider,
    project_manipulator_provider,
    util,
)

REQ_TIME = Summary("adjust_req_time", "time spent with adjust endpoint")
REQ_HISTOGRAM_TIME = Histogram(
    "adjust_req_histogram",
    "Histogram for adjust endpoint",
    buckets=[
        1,
        10,
        60,
        120,
        300,
        600,
        900,
        1200,
        1500,
        1800,
        2100,
        2400,
        2700,
        3000,
        3300,
        3600,
        4500,
        5400,
        6300,
        7200,
    ],
)

logger = logging.getLogger(__name__)

# Each adjust provider is represented by a get_*_provider factory function,
# which MUST return an adjust(repo_dir, extra_adjust_parameters, adjust_result) function.
#
# Each factory function takes various parameters that SHOULD be all derived from configuration.

git = git_provider.git_provider()
expect_ok = asutil.expect_ok_closure(exception.AdjustCommandError)


async def is_sync_on(adjustspec):
    """ For sync to be active, we need to both have the originRepoUrl information
        and the 'sync' key to be set to on.

        return: :bool: whether sync feature enabled or disabled
    """
    if (
        ("originRepoUrl" in adjustspec)
        and adjustspec["originRepoUrl"]
        and ("sync" in adjustspec)
        and (adjustspec["sync"] is True)
    ):
        logger.info("Auto-Sync feature activated")
        return True
    elif "originRepoUrl" not in adjustspec:
        logger.info("'originRepoUrl' key not specified: Auto-Sync feature disabled")
        return False
    elif not adjustspec["originRepoUrl"]:
        logger.info("'originRepoUrl' value is empty: Auto-Sync feature disabled")
        return False
    elif "sync" not in adjustspec:
        logger.info("'sync' key not specified: Auto-Sync feature disabled")
        return False
    else:  # sync key set to False
        logger.info("'sync' key set to False: Auto-Sync feature disabled")
        return False


async def check_ref_exists(work_dir, ref):
    is_tag = await git["is_tag"](work_dir, ref)
    if is_tag:
        return True

    is_branch = await git["is_branch"](work_dir, ref)
    if is_branch:
        return True

    is_sha = await git["does_sha_exist"](work_dir, ref)
    if is_sha:
        return True

    return False


async def sync_external_repo(adjustspec, repo_provider, work_dir, configuration):
    """ Get external repository and its ref into the internal repository
    """
    internal_repo_url = await repo_provider(adjustspec, create=False)
    git_user = configuration.get("git_username")

    await git["clone"](work_dir, adjustspec["originRepoUrl"])  # Clone origin

    # See NCL-4069: sometimes even with sync on, the upstream repo might not have the ref, but the downstream repo will
    # if ref exists on upstream repository, continue the sync as usual
    # if no, make sure ref exists on downstream repository, and checkout the correct repo
    # if no, then fail completely
    ref_exists = await check_ref_exists(work_dir, adjustspec["ref"])
    if ref_exists:
        await git["checkout"](work_dir, adjustspec["ref"], force=True)  # Checkout ref

        await git["rename_remote"](
            work_dir, "origin", "origin_remote"
        )  # Rename origin remote
        await git["add_remote"](
            work_dir,
            "origin",
            asutil.add_username_url(internal_repo_url.readwrite, git_user),
        )  # Add target remote

        ref = adjustspec["ref"]
        # Sync
        await clone.push_sync_changes(
            work_dir, ref, "origin", origin_remote="origin_remote"
        )

    else:
        logger.warn(
            "Upstream repository does not have the 'ref'. Trying to see if 'ref' present in downstream repository"
        )
        # Delete the upstreamed clone repository
        shutil.rmtree(work_dir)
        os.makedirs(work_dir)

        # Clone the internal repository
        await git["clone"](
            work_dir, asutil.add_username_url(internal_repo_url.readwrite, git_user)
        )  # Clone origin

        ref_exists = await check_ref_exists(work_dir, adjustspec["ref"])
        if ref_exists:
            logger.info(
                "Downstream repository has the ref, but not the upstream one. No syncing required!"
            )
            await git["checkout"](
                work_dir, adjustspec["ref"], force=True
            )  # Checkout ref
        else:
            logger.error(
                "Both upstream and downstream repository do not have the 'ref' present. Cannot proceed"
            )
            raise exception.AdjustCommandError(
                "Both upstream and downstream repository do not have the 'ref' present. Cannot proceed",
                [],
                exit_code=10,
            )

    # At this point the target repository might have the ref we want to sync, but the local repository might not have all the tags
    # from the target repository. We need to sync tags because we use it to know if we have tags with existing changes or if we
    # need to create tags of format <version>-<sha> if existing tag with name <version> exists after pme changes
    await git["fetch_tags"](work_dir, remote="origin")


@time(REQ_TIME)
@time(REQ_HISTOGRAM_TIME)
async def adjust(adjustspec, repo_provider):
    """
    This method executes adjust providers as specified in configuration.
    Returns a dictionary corresponding to the HTTP response content.
    """

    c = await config.get_configuration()

    adjust_result = {"adjustType": [], "resultData": {}}

    result = {}

    # By default the buildType is Maven
    build_type = "MVN"

    if "buildType" in adjustspec:
        logger.info("Build Type specified: " + adjustspec["buildType"])
        build_type = adjustspec["buildType"]

    with asutil.TemporaryDirectory(suffix="git") as work_dir:

        repo_url = await repo_provider(adjustspec, create=False)

        sync_enabled = await is_sync_on(adjustspec)
        if sync_enabled:
            await sync_external_repo(adjustspec, repo_provider, work_dir, c)
        else:
            git_user = c.get("git_username")

            await git["clone"](
                work_dir, asutil.add_username_url(repo_url.readwrite, git_user)
            )  # Clone origin
            await git["checkout"](
                work_dir, adjustspec["ref"], force=True
            )  # Checkout ref

        await asgit.setup_commiter(expect_ok, work_dir)

        ### Adjust Phase ###
        if build_type == "MVN":
            specific_tag_name = await adjust_mvn(work_dir, c, adjustspec, adjust_result)
        elif build_type == "GRADLE":
            specific_tag_name = await adjust_gradle(
                work_dir, c, adjustspec, adjust_result
            )
        else:
            specific_tag_name = await adjust_project_manip(
                work_dir, c, adjustspec, adjust_result
            )

        result = await commit_adjustments(
            repo_dir=work_dir,
            repo_url=repo_url,
            original_ref=adjustspec["ref"],
            adjust_type=", ".join(adjust_result["adjustType"]),
            force_continue_on_no_changes=True,
            specific_tag_name=specific_tag_name,
        )

        result = result if result is not None else {}

        result["adjustResultData"] = adjust_result["resultData"]
    return result


async def handle_temp_build(adjustspec, adjust_provider_config):
    temp_build_enabled = util.is_temp_build(adjustspec)
    logger.info("Temp build status: " + str(temp_build_enabled))

    specific_indy_group = util.get_specific_indy_group(
        adjustspec, adjust_provider_config
    )
    timestamp = util.get_temp_build_timestamp(adjustspec)

    if timestamp and not specific_indy_group:
        logger.error("Timestamp specified but specific indy group not specified!")
        logger.error("Timestamp: " + timestamp)

        raise Exception("Timestamp specified but specific indy group not specified!")

    return temp_build_enabled, timestamp, specific_indy_group


async def adjust_gradle(work_dir, c, adjustspec, adjust_result):
    logger.info("Using Gradle manipulation")

    adjust_provider_config = c.get("adjust", {}).get(
        gradle_provider.EXECUTION_NAME, None
    )

    if adjust_provider_config is None:
        raise Exception(
            "Adjust execution '{0}' configuration not available. Please add the '{0}' section to your configuration file".format(
                gradle_provider.EXECUTION_NAME
            )
        )

    temp_build_enabled, timestamp, specific_indy_group = await handle_temp_build(
        adjustspec, adjust_provider_config
    )

    for parameter in ["gradleAnalyzerPluginInitFilePath"]:
        if parameter not in adjust_provider_config:
            raise Exception(
                "Required {} configuration parameters: '{}' is missing in configuration file".format(
                    gradle_provider.EXECUTION_NAME, parameter
                )
            )

    default_parameters = adjust_provider_config.get("defaultParameters", [])
    extra_adjust_parameters = adjustspec.get("adjustParameters", {})

    result = await gradle_provider.get_gradle_provider(
        adjust_provider_config["gradleAnalyzerPluginInitFilePath"],
        adjust_provider_config["gradleAnalyzerPluginJarPath"],
        default_parameters,
        specific_indy_group,
        timestamp,
    )(work_dir, extra_adjust_parameters, adjust_result)

    return result["resultData"]["VersioningState"]["executionRootModified"]["version"]


async def adjust_mvn(work_dir, c, adjustspec, adjust_result):

    specific_tag_name = None

    executions = c.get("adjust", {}).get("executions", [])

    for execution_name in executions:
        adjust_provider_config = c.get("adjust", {}).get(execution_name, None)
        if adjust_provider_config is None:
            raise Exception(
                'Adjust execution "{execution_name}" configuration not available.'.format(
                    **locals()
                )
            )

        adjust_provider_name = adjust_provider_config.get("provider", None)
        extra_adjust_parameters = adjustspec.get("adjustParameters", {})

        if adjust_provider_name == "noop":
            await noop_provider.get_noop_provider(execution_name)(
                work_dir, extra_adjust_parameters, adjust_result
            )

        elif adjust_provider_name == "process":
            await process_provider.get_process_provider(
                execution_name,
                adjust_provider_config["cmd"],
                send_log=adjust_provider_config.get("outputToLogs", False),
            )(work_dir, extra_adjust_parameters, adjust_result)

        elif adjust_provider_name == "pme":
            (
                temp_build_enabled,
                timestamp,
                specific_indy_group,
            ) = await handle_temp_build(adjustspec, adjust_provider_config)

            pme_parameters = adjust_provider_config.get("defaultParameters", [])
            default_settings_parameters = adjust_provider_config.get(
                "defaultSettingsParameters", []
            )
            temporary_settings_parameters = adjust_provider_config.get(
                "temporarySettingsParameters", []
            )

            if temp_build_enabled:
                pme_parameters = temporary_settings_parameters + pme_parameters
            else:
                pme_parameters = default_settings_parameters + pme_parameters

            await pme_provider.get_pme_provider(
                execution_name,
                adjust_provider_config["cliJarPathAbsolute"],
                pme_parameters,
                adjust_provider_config.get("outputToLogs", False),
                specific_indy_group,
                timestamp,
            )(work_dir, extra_adjust_parameters, adjust_result)

            version = await pme_provider.get_version_from_pme_result(
                adjust_result["resultData"]
            )
            if version:
                specific_tag_name = version

        else:
            raise Exception(
                'Unknown adjust provider "{adjust_provider_name}".'.format(**locals())
            )

        adjust_result["adjustType"].append(execution_name)

        return specific_tag_name


async def adjust_project_manip(work_dir, c, adjustspec, adjust_result):

    specific_tag_name = None
    execution_name = "project-manipulator"

    adjust_provider_config = c.get("adjust", {}).get(execution_name, None)
    extra_adjust_parameters = adjustspec.get("adjustParameters", {})

    default_parameters = adjust_provider_config.get("defaultParameters", [])

    temp_build_enabled, timestamp, specific_indy_group = await handle_temp_build(
        adjustspec, adjust_provider_config
    )

    await project_manipulator_provider.get_project_manipulator_provider(
        execution_name,
        adjust_provider_config["cliJarPathAbsolute"],
        default_parameters,
        specific_indy_group,
        timestamp,
    )(work_dir, extra_adjust_parameters, adjust_result)

    # TODO: replace this with the real value
    version = await project_manipulator_provider.get_version_from_result(
        adjust_result["resultData"]
    )

    if version:
        specific_tag_name = version

    adjust_result["adjustType"].append(execution_name)

    return specific_tag_name


async def commit_adjustments(
    repo_dir,
    repo_url,
    original_ref,
    adjust_type,
    force_continue_on_no_changes=False,
    specific_tag_name=None,
):
    """
    Careful: Returns None if no changes were made, unless force_continue_on_no_changes is True
    """
    d = await asgit.push_new_dedup_branch(
        expect_ok=expect_ok,
        repo_dir=repo_dir,
        repo_url=repo_url,
        operation_name="Adjust",
        operation_description="""Tag automatically generated from Repour
Original Reference: {original_ref}
Adjust Type: {adjust_type}
""".format(
            **locals()
        ),
        no_change_ok=True,
        force_continue_on_no_changes=force_continue_on_no_changes,
        real_commit_time=True,
        specific_tag_name=specific_tag_name,
    )
    return d
