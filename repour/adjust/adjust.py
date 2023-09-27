# flake8: noqa
import asyncio
import logging
import os
import shutil

from prometheus_async.aio import time
from prometheus_client import Histogram, Summary

from repour.adjust.scala_provider import get_scala_provider
from repour import asutil, clone, exception
from repour.config import config
from repour.lib.logs import log_util
from repour.lib.scm import git, asgit

from repour.adjust import (
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

expect_ok = asutil.expect_ok_closure(exception.AdjustCommandError)


async def is_sync_on(adjustspec):
    """For sync to be active, we need to both have the originRepoUrl information
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
    is_tag = await git.is_tag(work_dir, ref)
    if is_tag:
        return True

    is_branch = await git.is_branch(work_dir, ref)
    if is_branch:
        return True

    is_sha = await git.does_sha_exist(work_dir, ref)
    if is_sha:
        return True

    is_pr = await git.does_pr_exist(work_dir, ref)
    if is_pr:
        return True

    return False


async def sync_external_repo(adjustspec, repo_provider, work_dir, configuration):
    """Get external repository and its ref into the internal repository

    return: <bool> indicate if ref is only in downstream repo (True) or is also present in upstream repo (False)
    """
    internal_repo_url = await repo_provider(adjustspec, create=False)
    git_user = configuration.get("git_username")
    git_origin_repo_urls_internal = configuration.get(
        "git_origin_repo_urls_internal", []
    )

    is_ref_revision_internal = True

    await git.clone(work_dir, adjustspec["originRepoUrl"])  # Clone origin

    # See NCL-4069: sometimes even with sync on, the upstream repo might not have the ref, but the downstream repo will
    # if ref exists on upstream repository, continue the sync as usual
    # if no, make sure ref exists on downstream repository, and checkout the correct repo
    # if no, then fail completely
    ref_exists = await check_ref_exists(work_dir, adjustspec["ref"])
    if ref_exists:

        is_ref_revision_internal = False

        is_pull_request = git.is_ref_a_pull_request(adjustspec["ref"])

        if is_pull_request:
            await git.checkout_pr(work_dir, adjustspec["ref"])
        else:
            await git.checkout(work_dir, adjustspec["ref"], force=True)  # Checkout ref

        await git.rename_remote(
            work_dir, "origin", "origin_remote"
        )  # Rename origin remote
        await git.add_remote(
            work_dir,
            "origin",
            asutil.add_username_url(internal_repo_url.readwrite, git_user),
        )  # Add target remote

        ref = adjustspec["ref"]
        # Sync
        if is_pull_request:
            logger.info(
                "Syncing of Pull Request to downstream repository disabled since the ref is a pull request"
            )
        else:
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
        await git.clone(
            work_dir, asutil.add_username_url(internal_repo_url.readwrite, git_user)
        )  # Clone origin

        ref_exists = await check_ref_exists(work_dir, adjustspec["ref"])
        if ref_exists:
            logger.info(
                "Downstream repository has the ref, but not the upstream one. No syncing required!"
            )
            await git.checkout(work_dir, adjustspec["ref"], force=True)  # Checkout ref
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
    await git.fetch_tags(work_dir, remote="origin")

    # [NCL-6947] irrespective of the value of is_ref_revision_internal, if the originRepoUrl matches one of the urls in the config
    # 'git_origin_repo_urls_internal', the ref must be considered internal
    for url in git_origin_repo_urls_internal:
        if url in adjustspec["originRepoUrl"]:
            is_ref_revision_internal = True
            break

    return is_ref_revision_internal


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

    verify_only_authorized_urls_used(adjustspec, c)

    # By default the buildType is Maven
    build_type = "MVN"

    if "buildType" in adjustspec:
        logger.info("Build Type specified: " + adjustspec["buildType"])
        build_type = adjustspec["buildType"]

    with asutil.TemporaryDirectory(suffix="git") as work_dir:

        repo_url = await repo_provider(adjustspec, create=False)

        process_mdc("BEGIN", "SCM_CLONE")
        sync_enabled = await is_sync_on(adjustspec)
        is_ref_revision_internal = True
        if sync_enabled:
            is_ref_revision_internal = await sync_external_repo(
                adjustspec, repo_provider, work_dir, c
            )
        else:
            git_user = c.get("git_username")

            await git.clone(
                work_dir, asutil.add_username_url(repo_url.readwrite, git_user)
            )  # Clone origin
            await git.checkout(work_dir, adjustspec["ref"], force=True)  # Checkout ref

        upstream_commit_id = await git.rev_parse(work_dir)

        await asgit.setup_commiter(expect_ok, work_dir)
        await asgit.transform_git_submodule_into_fat_repository(work_dir)
        process_mdc("END", "SCM_CLONE")

        commit_id = await git.show_current_commit(work_dir)
        logger.info("Current Commit ID of repo is: " + commit_id)

        process_mdc("BEGIN", "ALIGNMENT_ADJUST")

        ### Adjust Phase ###
        if build_type == "MVN":
            specific_tag_name = await adjust_mvn(work_dir, c, adjustspec, adjust_result)
        elif build_type == "GRADLE":
            specific_tag_name = await adjust_gradle(
                work_dir, c, adjustspec, adjust_result
            )
        elif build_type == "SBT":
            specific_tag_name = await adjust_scala(
                work_dir, c, adjustspec, adjust_result
            )
        else:
            specific_tag_name = await adjust_project_manip(
                work_dir, c, adjustspec, adjust_result
            )

        is_pull_request = git.is_ref_a_pull_request(adjustspec["ref"])

        # if we are aligning from a PR, indicate it as such in the tag name
        if is_pull_request:
            specific_tag_name = "Pull_Request-" + specific_tag_name

        result = await commit_adjustments(
            repo_dir=work_dir,
            repo_url=repo_url,
            original_ref=adjustspec["ref"],
            adjust_type=", ".join(adjust_result["adjustType"]),
            force_continue_on_no_changes=True,
            specific_tag_name=specific_tag_name,
        )

        result = result if result is not None else {}

        result["upstream_commit"] = upstream_commit_id
        result["is_ref_revision_internal"] = is_ref_revision_internal

        result["adjustResultData"] = adjust_result["resultData"]
        process_mdc("END", "ALIGNMENT_ADJUST")
    return result


async def handle_build_mode(adjustspec, adjust_config):
    build_category_key = "BUILD_CATEGORY"

    build_category = adjustspec.get("adjustParameters", {}).get(
        build_category_key, "STANDARD"
    )

    build_category_config = adjust_config.get("buildCategories", {}).get(
        build_category, None
    )
    if build_category_config is None:
        logger.error("Unknown build category!")
        logger.error("Build category: " + build_category)
        raise Exception("Unknown build category!")

    temp_build_enabled = util.is_temp_build(adjustspec)
    temp_build_prefer_persistent = util.is_alignment_preference(
        adjustspec, "PREFER_PERSISTENT"
    )
    brew_pull_enabled = util.has_key_true(adjustspec, "brewPullActive")
    suffix_prefix = util.get_build_version_suffix_prefix(
        build_category_config, temp_build_enabled
    )

    logger.info("Build category: " + build_category)
    logger.info("Temp build status: " + str(temp_build_enabled))
    logger.info("Brew pull status: " + str(brew_pull_enabled))

    if temp_build_enabled:
        if temp_build_prefer_persistent:
            rest_mode = build_category_config["temporary_prefer_persistent_mode"]
        else:
            rest_mode = build_category_config["temporary_mode"]
    else:
        rest_mode = build_category_config["persistent_mode"]

    return (
        temp_build_enabled,
        suffix_prefix,
        rest_mode,
        brew_pull_enabled,
        temp_build_prefer_persistent,
    )


async def adjust_gradle(work_dir, c, adjustspec, adjust_result):
    logger.info("Using Gradle manipulation")

    adjust_config = c.get("adjust", {})
    adjust_provider_config = adjust_config.get(gradle_provider.EXECUTION_NAME, None)

    if adjust_provider_config is None:
        raise Exception(
            "Adjust execution '{0}' configuration not available. Please add the '{0}' section to your configuration file".format(
                gradle_provider.EXECUTION_NAME
            )
        )

    (
        temp_build_enabled,
        suffix_prefix,
        rest_mode,
        brew_pull_enabled,
        temp_prefer_persistent_enabled,
    ) = await handle_build_mode(adjustspec, adjust_config)

    for parameter in ["gradleAnalyzerPluginInitFilePath"]:
        if parameter not in adjust_provider_config:
            raise Exception(
                "Required {} configuration parameters: '{}' is missing in configuration file".format(
                    gradle_provider.EXECUTION_NAME, parameter
                )
            )

    repour_parameters = adjust_provider_config.get("defaultParameters", [])
    default_parameters = get_default_alignment_parameters(adjustspec)
    extra_adjust_parameters = adjustspec.get("adjustParameters", {})

    result = await gradle_provider.get_gradle_provider(
        adjust_provider_config["gradleAnalyzerPluginInitFilePath"],
        adjust_provider_config["gradleAnalyzerPluginJarPath"],
        default_parameters,
        repour_parameters,
        adjust_provider_config["defaultGradlePath"],
        rest_mode,
        brew_pull_enabled,
        suffix_prefix,
        temp_prefer_persistent_enabled,
    )(work_dir, extra_adjust_parameters, adjust_result)

    return result["resultData"]["VersioningState"]["executionRootModified"]["version"]


async def adjust_mvn(work_dir, c, adjustspec, adjust_result):

    specific_tag_name = None

    executions = c.get("adjust", {}).get("executions", [])

    for execution_name in executions:
        adjust_config = c.get("adjust", {})
        adjust_provider_config = adjust_config.get(execution_name, None)
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
                suffix_prefix,
                rest_mode,
                brew_pull_enabled,
                temp_prefer_persistent_enabled,
            ) = await handle_build_mode(adjustspec, adjust_config)

            # unrewritable repour PME parameters
            repour_parameters = adjust_provider_config.get("defaultParameters", [])

            # path of repour settings.xml for permanent builds
            default_settings_parameters = adjust_provider_config.get(
                "defaultSettingsParameters", []
            )

            # path of repour settings.xml for temporary builds
            temporary_settings_parameters = adjust_provider_config.get(
                "temporarySettingsParameters", []
            )

            if temp_build_enabled:
                pme_parameters = (
                    temporary_settings_parameters
                    + get_default_alignment_parameters(adjustspec)
                )
            else:
                pme_parameters = (
                    default_settings_parameters
                    + get_default_alignment_parameters(adjustspec)
                )

            await pme_provider.get_pme_provider(
                execution_name,
                adjust_provider_config["cliJarPathAbsolute"],
                pme_parameters,
                repour_parameters,
                rest_mode,
                adjust_provider_config.get("outputToLogs", False),
                brew_pull_enabled,
                suffix_prefix,
                temp_prefer_persistent_enabled,
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
    adjust_config = c.get("adjust", {})
    adjust_provider_config = adjust_config.get(execution_name, None)
    extra_adjust_parameters = adjustspec.get("adjustParameters", {})

    # unrewritable repour project-manipulator parameters
    repour_parameters = adjust_provider_config.get("defaultParameters", [])
    # default project-manipulator parameters from build config
    default_parameters = get_default_alignment_parameters(adjustspec)

    (
        temp_build_enabled,
        suffix_prefix,
        rest_mode,
        brew_pull_enabled,
        temp_prefer_persistent_enabled,
    ) = await handle_build_mode(adjustspec, adjust_config)

    await project_manipulator_provider.get_project_manipulator_provider(
        execution_name,
        adjust_provider_config["cliJarPathAbsolute"],
        default_parameters,
        repour_parameters,
        rest_mode,
        suffix_prefix,
    )(work_dir, extra_adjust_parameters, adjust_result)

    # TODO: replace this with the real value
    version = await project_manipulator_provider.get_version_from_result(
        adjust_result["resultData"]
    )

    if version:
        specific_tag_name = version

    adjust_result["adjustType"].append(execution_name)

    return specific_tag_name


async def adjust_scala(work_dir, c, adjustspec, adjust_result):
    logger.info("Using Scala manipulation")

    execution_name = "SBT"
    adjust_config = c.get("adjust", {})
    adjust_provider_config = adjust_config.get(execution_name, None)
    extra_adjust_parameters = adjustspec.get("adjustParameters", {})

    repour_parameters = adjust_provider_config.get("defaultParameters", [])
    default_parameters = get_default_alignment_parameters(adjustspec)

    (
        temp_build_enabled,
        suffix_prefix,
        rest_mode,
        brew_pull_enabled,
        temp_prefer_persistent_enabled,
    ) = await handle_build_mode(adjustspec, adjust_config)

    result = await get_scala_provider(
        execution_name,
        adjust_provider_config["sbtPathAbsolute"],
        default_parameters,
        repour_parameters,
        rest_mode,
        brew_pull_enabled,
        suffix_prefix,
    )(work_dir, extra_adjust_parameters, adjust_result)

    return result["resultData"]["VersioningState"]["executionRootModified"]["version"]


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


def process_mdc(step, name):
    log_util.add_update_mdc_key_value_in_task("process_stage_name", name)
    log_util.add_update_mdc_key_value_in_task("process_stage_step", step)

    # set the logger to what we want
    current_logger_name = getattr(asyncio.current_task(), "loggerName", None)
    # NCL-7133: use different logger name for process stage update
    asyncio.current_task().loggerName = "org.jboss.pnc._userlog_.process-stage-update"
    logger.info(step + ": " + name)
    if current_logger_name:
        asyncio.current_task().loggerName = current_logger_name

    # Remove the fields now
    log_util.remove_mdc_key_in_task("process_stage_step")
    log_util.remove_mdc_key_in_task("process_stage_name")


def verify_only_authorized_urls_used(adjustspec, c):
    """
    If the alignment parameters contain non-authorized urls, an exception is thrown
    """

    authorized_url_root = c.get("adjust_authorized_url")

    extra_adjust_parameters = adjustspec.get("adjustParameters", {})
    text = extra_adjust_parameters.get("ALIGNMENT_PARAMETERS", "")

    non_authorized_urls = asutil.list_non_origin_urls_from_string(
        authorized_url_root, text
    )

    if len(non_authorized_urls) > 0:
        logger.error(
            "The adjust parameters contain non-authorized urls: '{}'. Url has to be from: {}".format(
                non_authorized_urls, authorized_url_root
            )
        )
        raise exception.CommandError(
            "Non-authorized urls used in adjust parameters",
            [],
            10,
            "",
            "Non-authorized urls used in adjust parameters",
        )


def get_default_alignment_parameters(adjustspec):
    """
    Helper method to extract default alignment parameters as passed in spec and return values in a list.

    for e.g if the params is passed as "key=value key2=value2", then the returned list will be:
        ["key=value", "key2=value2"]
    """

    default_alignment_parameters = []

    if (
        "defaultAlignmentParams" in adjustspec
        and adjustspec["defaultAlignmentParams"] is not None
    ):
        default_alignment_parameters = adjustspec["defaultAlignmentParams"].split()

    return default_alignment_parameters
