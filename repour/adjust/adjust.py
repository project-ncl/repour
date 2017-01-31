import asyncio
import logging

from . import noop_provider
from . import pme_provider
from . import process_provider
from .. import asgit
from .. import asutil
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
def adjust(adjustspec, repo_provider):
    """
    This method executes adjust providers as specified in configuration.
    Returns a dictionary corresponding to the HTTP response content.
    """
    c = yield from config.get_configuration()
    executions = c.get("adjust", {}).get("executions", [])

    adjust_result = {
        "adjustType": [],
        "resultData": {}
    }

    result = {}

    with asutil.TemporaryDirectory(suffix="git") as work_dir:

        repo_url = yield from repo_provider(adjustspec, create=False)

        yield from git["clone_checkout_branch_tag_shallow"](work_dir, repo_url.readwrite, adjustspec["ref"])

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
                yield from pme_provider.get_pme_provider(execution_name,
                                                         adjust_provider_config["cliJarPathAbsolute"],
                                                         adjust_provider_config.get("defaultParameters", []),
                                                         adjust_provider_config.get("outputToLogs", False)) \
                    (work_dir, extra_adjust_parameters, adjust_result)

            else:
                raise Exception("Unknown adjust provider \"{adjust_provider_name}\".".format(**locals()))

            adjust_result["adjustType"].append(execution_name)

        result = yield from commit_adjustments(
            repo_dir=work_dir,
            repo_url=repo_url,
            original_ref=adjustspec["ref"],
            adjust_type=", ".join(adjust_result["adjustType"]),
            force_continue_on_no_changes=True
        )

        result = result if result is not None else {}

        result["adjustResultData"] = adjust_result["resultData"]
    return result


@asyncio.coroutine
def commit_adjustments(repo_dir, repo_url, original_ref, adjust_type, force_continue_on_no_changes=False):
    """
    Careful: Returns None if no changes were made, unless force_continue_on_no_changes is True
    """
    d = yield from asgit.push_new_dedup_branch(
        expect_ok=expect_ok,
        repo_dir=repo_dir,
        repo_url=repo_url,
        operation_name="Adjust",
        operation_description="""Original Reference: {original_ref}
Adjust Type: {adjust_type}
""".format(**locals()),
        no_change_ok=True,
        force_continue_on_no_changes=force_continue_on_no_changes
    )
    return d
