import asyncio
import logging

from . import noop_provider
from . import pme_provider
from . import process_provider
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
def is_temp_build(adjustspec):
    """ For temp build to be active, we need to both provide a 'is_temp_build' key
        in our request and its value must be true

        return: :bool: whether temp build feature enabled or not
    """
    key = 'tempBuild'
    if (key in adjustspec) and adjustspec[key] is True:
        return True
    else:
        return False

@asyncio.coroutine
def get_specific_indy_group(adjustspec, adjust_provider_config):
    temp_build_enabled = yield from is_temp_build(adjustspec)

    if temp_build_enabled:
        return adjust_provider_config.get("temp_build_indy_group", None)
    else:
        return None

@asyncio.coroutine
def get_temp_build_timestamp(adjustspec):
    """ Find the timestamp to provide to PME from the adjust request.

        If the timestamp is set *AND* the temp_build key is set to true, then
        this function returns the value of the timestamp.

        Otherwise it will return None
    """
    temp_build_timestamp_key = 'tempBuildTimestamp'
    temp_build_timestamp = None

    temp_build_enabled = yield from is_temp_build(adjustspec)

    if temp_build_timestamp_key in adjustspec:
        temp_build_timestamp = adjustspec[temp_build_timestamp_key]

    if temp_build_timestamp is None:
        temp_build_timestamp = "temporary"

    if temp_build_enabled:
        logger.info("Temp build timestamp set to: " + str(temp_build_timestamp))
        return temp_build_timestamp
    else:
        return None

@asyncio.coroutine
def sync_external_repo(adjustspec, repo_provider, work_dir, configuration):
    """ Get external repository and its ref into the internal repository
    """
    internal_repo_url = yield from repo_provider(adjustspec, create=False)
    git_user = configuration.get("git_username")

    yield from git["clone"](work_dir, adjustspec["originRepoUrl"])  # Clone origin
    yield from git["checkout"](work_dir, adjustspec["ref"])  # Checkout ref
    yield from git["remove_remote"](work_dir, "origin")  # Remove origin remote
    yield from git["add_remote"](work_dir, "origin", asutil.add_username_url(internal_repo_url.readwrite, git_user))  # Add target remote

    ref = adjustspec["ref"]
    yield from clone.push_sync_changes(work_dir, ref, "origin")

@asyncio.coroutine
def adjust(adjustspec, repo_provider):
    """
    This method executes adjust providers as specified in configuration.
    Returns a dictionary corresponding to the HTTP response content.
    """
    specific_tag_name = None

    c = yield from config.get_configuration()
    executions = c.get("adjust", {}).get("executions", [])

    adjust_result = {
        "adjustType": [],
        "resultData": {}
    }

    result = {}

    with asutil.TemporaryDirectory(suffix="git") as work_dir:

        repo_url = yield from repo_provider(adjustspec, create=False)

        sync_enabled = yield from is_sync_on(adjustspec)
        if sync_enabled:
            yield from sync_external_repo(adjustspec, repo_provider, work_dir, c)
        else:
            git_user = c.get("git_username")

            yield from git["clone"](work_dir, asutil.add_username_url(repo_url.readwrite, git_user))  # Clone origin
            yield from git["checkout"](work_dir, adjustspec["ref"])  # Checkout ref

        ### Adjust Phase ###
        yield from asgit.setup_commiter(expect_ok, work_dir)

        for execution_name in executions:
            adjust_provider_config = c.get("adjust", {}).get(execution_name, None)
            if adjust_provider_config is None:
                raise Exception("Adjust execution \"{execution_name}\" configuration not available.".format(**locals()))

            adjust_provider_name = adjust_provider_config.get("provider", None)
            extra_adjust_parameters = adjustspec.get("adjustParameters", {})

            if adjust_provider_name == "noop":
                yield from noop_provider.get_noop_provider(execution_name) \
                    (work_dir, extra_adjust_parameters, adjust_result)

            elif adjust_provider_name == "process":
                yield from process_provider.get_process_provider(execution_name,
                                                                 adjust_provider_config["cmd"],
                                                                 send_log=adjust_provider_config.get("outputToLogs",
                                                                                                     False)) \
                    (work_dir, extra_adjust_parameters, adjust_result)

            elif adjust_provider_name == "pme":

                temp_build_enabled = yield from is_temp_build(adjustspec)
                logger.info("Temp build status: " + str(temp_build_enabled))

                specific_indy_group = yield from get_specific_indy_group(adjustspec, adjust_provider_config)
                timestamp = yield from get_temp_build_timestamp(adjustspec)
                yield from pme_provider.get_pme_provider(execution_name,
                                                         adjust_provider_config["cliJarPathAbsolute"],
                                                         adjust_provider_config.get("defaultParameters", []),
                                                         adjust_provider_config.get("outputToLogs", False),
                                                         specific_indy_group, timestamp) \
                    (work_dir, extra_adjust_parameters, adjust_result)

                version = yield from pme_provider.get_version_from_pme_result(adjust_result['resultData'])
                if version:
                    specific_tag_name = version

            else:
                raise Exception("Unknown adjust provider \"{adjust_provider_name}\".".format(**locals()))

            adjust_result["adjustType"].append(execution_name)

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
