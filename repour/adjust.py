import asyncio
import io
import json
import logging
import os
import zipfile

from .scm import git_provider
from . import asgit
from . import asutil
from . import exception

logger = logging.getLogger(__name__)

#
# Utility
#

def log_executable_info(cmd):
    first = True
    for c in cmd:
        if c.endswith(".jar"):
            manifest = {}
            try:
                with zipfile.ZipFile(c) as z:
                    with z.open("META-INF/MANIFEST.MF") as bf:
                        f = io.TextIOWrapper(bf)
                        raw_lines = f.readlines()
                        previous_k = None
                        for line in raw_lines:
                            if line.startswith(" "):
                                assert previous_k is not None
                                manifest[previous_k] += line.strip()
                            elif line == "\n":
                                pass
                            else:
                                k,v = line.rstrip().split(":", 1)
                                manifest[k] = v.lstrip()
                                previous_k = k
            except FileNotFoundError:
                pass
            except KeyError:
                pass
            else:
                basename = os.path.basename(c)
                title = manifest.get("Implementation-Title", "Unknown")
                version = manifest.get("Implementation-Version", "Unknown")
                logger.info("adjust provider jar: {basename}, {title}, {version}".format(**locals()))

expect_ok = asutil.expect_ok_closure(exception.AdjustCommandError)

@asyncio.coroutine
def commit_adjustments(repo_dir, repo_url, original_ref, adjust_type):
    d = yield from asgit.push_new_dedup_branch(
        expect_ok=expect_ok,
        repo_dir=repo_dir,
        repo_url=repo_url,
        operation_name="Adjust",
        operation_description="""Original Reference: {original_ref}
Adjust Type: {adjust_type}
""".format(**locals()),
        no_change_ok=True,
    )
    return d

#
# Adjust operation
#

git = git_provider.git_provider()

@asyncio.coroutine
def adjust(adjustspec, repo_provider, adjust_provider):
    with asutil.TemporaryDirectory(suffix="git") as work_dir:
        repo_url = yield from repo_provider(adjustspec, create=False)

        # Non-shallow, but branch-only clone of internal repo
        yield from git["clone_checkout_branch_tag_deep"](work_dir, repo_url.readwrite, adjustspec["ref"])

        yield from asgit.setup_commiter(expect_ok, work_dir)
        adjust_result_data = yield from adjust_provider(work_dir)
        result = yield from commit_adjustments(
            repo_dir=work_dir,
            repo_url=repo_url,
            original_ref=adjustspec["ref"],
            adjust_type=adjust_result_data["adjustType"],
        )
        result["adjustResultData"] = adjust_result_data["resultData"]

    return result or {}

#
# Adjust providers
#

def adjust_noop():
    logger.info("Using noop adjust provider")
    @asyncio.coroutine
    def adjust(repo_dir):
        return {"adjustType": "NoOp", "resultData": "{}"}
    return adjust

def adjust_subprocess(description, cmd, log_context_option=None, send_log=False):
    logger.info("Using subprocess adjust provider, Description: {description} CMD: {cmd}".format(**locals()))
    log_executable_info(cmd)

    @asyncio.coroutine
    def get_result_data(work_dir):
        raw_result_data = "{}"
        # This is PME specific. TODO Refactor adjust providers.
        result_file_path = work_dir + "/target/pom-manip-ext-result.json"
        if os.path.isfile(result_file_path):
            with open(result_file_path, "r") as file:
                raw_result_data = file.read()
        return json.loads(raw_result_data)

    @asyncio.coroutine
    def adjust(repo_dir):
        filled_cmd = [p.format(repo_dir=repo_dir) if p.startswith("{repo_dir}") else p for p in cmd]

        log_context = getattr(asyncio.Task.current_task(), "log_context", None)
        if log_context_option is None:
            if log_context is None:
                env = None
            else:
                env = {
                    "LOG_CONTEXT": asyncio.Task.current_task().log_context,
                }
        else:
            env = None
            if log_context is not None:
                filled_cmd.append(log_context_option)
                filled_cmd.append(log_context)

        logger.info("Executing adjust subprocess")
        try:
            yield from expect_ok(
                cmd=filled_cmd,
                desc="Alignment subprocess failed",
                cwd=repo_dir,
                env=env,
                stdout="send" if send_log else "capture",
                stderr="stdout" if send_log else "log_on_error",
            )
        except exception.CommandError as e:
            logger.error("Adjust subprocess failed, exited code {e.exit_code}".format(**locals()))
            raise

        logger.info("Adjust subprocess exited ok")
        adjust_result_data = {}
        adjust_result_data["adjustType"] = description
        adjust_result_data["resultData"] = yield from get_result_data(repo_dir)
        return adjust_result_data
    return adjust

#
# Supported
#

provider_types = {
    "noop": adjust_noop,
    "subprocess": adjust_subprocess,
}
