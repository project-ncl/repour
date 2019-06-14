import asyncio
import logging
import os
import shutil

from . import gradle_provider
from . import noop_provider
from . import pme_provider
from . import process_provider
from . import util

from .. import asgit
from .. import asutil
from .. import clone
from .. import exception
from ..config import config
from ..scm import git_provider

logger = logging.getLogger(__name__)

# Each adjust provider is represented by a get_*_provider factory function,
# which MUST return an adjust(repo_dir, extra_adjust_parameters, adjust_result) function.
#
# Each factory function takes various parameters that SHOULD be all derived from configuration.

git = git_provider.git_provider()
expect_ok = asutil.expect_ok_closure(exception.AdjustCommandError)

@asyncio.coroutine
def is_sync_on(adjustspec):
    """ For sync to be active, we need to both have the originRepoUrl information
        and the 'sync' key to be set to on.

        return: :bool: whether sync feature enabled or disabled
    """
    if ('originRepoUrl' in adjustspec) and adjustspec['originRepoUrl'] and ('sync' in adjustspec) and (adjustspec['sync'] is True):
        logger.info('Auto-Sync feature activated')
        return True
    elif ('originRepoUrl' not in adjustspec):
        logger.info("'originRepoUrl' key not specified: Auto-Sync feature disabled")
        return False
    elif not adjustspec['originRepoUrl']:
        logger.info("'originRepoUrl' value is empty: Auto-Sync feature disabled")
        return False
    elif ('sync' not in adjustspec):
        logger.info("'sync' key not specified: Auto-Sync feature disabled")
        return False
    else: # sync key set to False
        logger.info("'sync' key set to False: Auto-Sync feature disabled")
        return False

@asyncio.coroutine
def check_ref_exists(work_dir, ref):
    is_tag = yield from git["is_tag"](work_dir, ref)
    if is_tag:
        return True

    is_branch = yield from git["is_branch"](work_dir, ref)
    if is_branch:
        return True

    is_sha = yield from git["does_sha_exist"](work_dir, ref)
    if is_sha:
        return True

    return False

@asyncio.coroutine
def sync_external_repo(adjustspec, repo_provider, work_dir, configuration):
    """ Get external repository and its ref into the internal repository
    """
    internal_repo_url = yield from repo_provider(adjustspec, create=False)
    git_user = configuration.get("git_username")

    yield from git["clone"](work_dir, adjustspec["originRepoUrl"])  # Clone origin

    # See NCL-4069: sometimes even with sync on, the upstream repo might not have the ref, but the downstream repo will
    # if ref exists on upstream repository, continue the sync as usual
    # if no, make sure ref exists on downstream repository, and checkout the correct repo
    # if no, then fail completely
    ref_exists = yield from check_ref_exists(work_dir, adjustspec["ref"])
    if ref_exists:
        yield from git["checkout"](work_dir, adjustspec["ref"], force=True)  # Checkout ref

        yield from git["rename_remote"](work_dir, "origin", "origin_remote")  # Rename origin remote
        yield from git["add_remote"](work_dir, "origin", asutil.add_username_url(internal_repo_url.readwrite, git_user))  # Add target remote

        ref = adjustspec["ref"]
        # Sync
        yield from clone.push_sync_changes(work_dir, ref, "origin", origin_remote="origin_remote")

    else:
        logger.warn("Upstream repository does not have the 'ref'. Trying to see if 'ref' present in downstream repository")
        # Delete the upstreamed clone repository
        shutil.rmtree(work_dir)
        os.makedirs(work_dir)

        # Clone the internal repository
        yield from git["clone"](work_dir, asutil.add_username_url(internal_repo_url.readwrite, git_user))  # Clone origin

        ref_exists = yield from check_ref_exists(work_dir, adjustspec["ref"])
        if ref_exists:
            logger.info("Downstream repository has the ref, but not the upstream one. No syncing required!")
            yield from git["checkout"](work_dir, adjustspec["ref"], force=True)  # Checkout ref
        else:
            logger.error("Both upstream and downstream repository do not have the 'ref' present. Cannot proceed")
            raise exception.AdjustCommandError("Both upstream and downstream repository do not have the 'ref' present. Cannot proceed",
                                         [], exit_code=10)



    # At this point the target repository might have the ref we want to sync, but the local repository might not have all the tags
    # from the target repository. We need to sync tags because we use it to know if we have tags with existing changes or if we
    # need to create tags of format <version>-<sha> if existing tag with name <version> exists after pme changes
    yield from git["fetch_tags"](work_dir, remote="origin")

@asyncio.coroutine
def handle_temp_build(adjustspec, adjust_provider_config):
    temp_build_enabled = yield from util.is_temp_build(adjustspec)
    logger.info("Temp build status: " + str(temp_build_enabled))

    specific_indy_group = yield from util.get_specific_indy_group(adjustspec, adjust_provider_config)
    timestamp = yield from util.get_temp_build_timestamp(adjustspec)

    if timestamp and not specific_indy_group:
        logger.error('Timestamp specified but specific indy group not specified!')
        logger.error('Timestamp: ' + timestamp)

        raise Exception('Timestamp specified but specific indy group not specified!')

    return temp_build_enabled, timestamp, specific_indy_group

@asyncio.coroutine
def adjust(adjustspec, repo_provider):
    """
    This method executes adjust providers as specified in configuration.
    Returns a dictionary corresponding to the HTTP response content.
    """
    specific_tag_name = None

    c = yield from config.get_configuration()

    adjust_result = {
        "adjustType": [],
        "resultData": {}
    }

    result = {}

    # The adjust body is missing the buildType key, exit early
    if 'buildType' not in adjustspec:
        raise Exception("No build type specified in adjust body: buildType key is missing")

    buildType = adjustspec["buildType"]

    # There is no configuration for the specific build type provider found in the Repour config file, exit early
    if buildType not in c.get("adjust", {}):
        raise Exception("Adjust provider for \"{buildType}\" build type could not be found.".format(**locals()))

    with asutil.TemporaryDirectory(suffix="git") as work_dir:

        repo_url = yield from repo_provider(adjustspec, create=False)

        sync_enabled = yield from is_sync_on(adjustspec)
        if sync_enabled:
            yield from sync_external_repo(adjustspec, repo_provider, work_dir, c)
        else:
            git_user = c.get("git_username")

            yield from git["clone"](work_dir, asutil.add_username_url(repo_url.readwrite, git_user))  # Clone origin
            yield from git["checkout"](work_dir, adjustspec["ref"], force=True)  # Checkout ref

        ### Adjust Phase ###
        yield from asgit.setup_commiter(expect_ok, work_dir)

        adjust_provider_config = c.get("adjust", {}).get(buildType, None)

        if adjust_provider_config is None:
            raise Exception("Adjust execution \"{buildType}\" configuration not available.".format(**locals()))

        temp_build_enabled, timestamp, specific_indy_group = yield from handle_temp_build(adjustspec, adjust_provider_config)

        extra_adjust_parameters = adjustspec.get("adjustParameters", {})

        if buildType == "NPM":
            yield from process_provider.get_process_provider("process",
                                                                adjust_provider_config["cmd"],
                                                                send_log=adjust_provider_config.get("outputToLogs",
                                                                                                    False)) \
                (work_dir, extra_adjust_parameters, adjust_result)
        elif buildType == "GRADLE":
            logger.info("Using Gradle manipulation")

            for parameter in ["gradleAnalyzerPluginInitFilePath"]:
                if parameter not in adjust_provider_config:
                    raise Exception("Required {} configuration parameter: '{}' is missing in the Repour configuration file".format(buildType, parameter))

            default_parameters = adjust_provider_config.get("defaultParameters", [])

            adjust_result = yield from gradle_provider.get_gradle_provider(adjust_provider_config["gradleAnalyzerPluginInitFilePath"], default_parameters, specific_indy_group, timestamp) \
                (work_dir, extra_adjust_parameters, adjust_result)

            specific_tag_name = adjust_result["resultData"]["VersioningState"]["executionRootModified"]["version"]

        elif buildType == "MVN":
            pme_parameters = adjust_provider_config.get("defaultParameters", [])
            default_settings_parameters = adjust_provider_config.get("defaultSettingsParameters", [])
            temporary_settings_parameters = adjust_provider_config.get("temporarySettingsParameters", [])

            if temp_build_enabled:
                pme_parameters = temporary_settings_parameters + pme_parameters
            else:
                pme_parameters = default_settings_parameters + pme_parameters


            yield from pme_provider.get_pme_provider("pme",
                                                        adjust_provider_config["cliJarPathAbsolute"],
                                                        pme_parameters,
                                                        adjust_provider_config.get("outputToLogs", False),
                                                        specific_indy_group, timestamp) \
                (work_dir, extra_adjust_parameters, adjust_result)

            version = yield from pme_provider.get_version_from_pme_result(adjust_result['resultData'])
            if version:
                specific_tag_name = version

        else:
            raise Exception("Unknown build type \"{buildType}\".".format(**locals()))

        result = yield from commit_adjustments(
            repo_dir=work_dir,
            repo_url=repo_url,
            original_ref=adjustspec["ref"],
            adjust_type=", ".join(adjust_result["adjustType"]),
            force_continue_on_no_changes=True,
            specific_tag_name=specific_tag_name
        )

        result = result if result is not None else {}

        result["adjustResultData"] = adjust_result["resultData"]
    return result

@asyncio.coroutine
def commit_adjustments(repo_dir, repo_url,
                       original_ref, adjust_type,
                       force_continue_on_no_changes=False,
                       specific_tag_name=None):
    """
    Careful: Returns None if no changes were made, unless force_continue_on_no_changes is True
    """
    d = yield from asgit.push_new_dedup_branch(
        expect_ok=expect_ok,
        repo_dir=repo_dir,
        repo_url=repo_url,
        operation_name="Adjust",
        operation_description="""Tag automatically generated from Repour
Original Reference: {original_ref}
Adjust Type: {adjust_type}
""".format(**locals()),
        no_change_ok=True,
        force_continue_on_no_changes=force_continue_on_no_changes,
        real_commit_time=True,
        specific_tag_name=specific_tag_name,
    )
    return d
