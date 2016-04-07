import asyncio
import io
import logging
import os
import zipfile

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

@asyncio.coroutine
def adjust(adjustspec, repo_provider, adjust_provider):
    with asutil.TemporaryDirectory(suffix="git") as d:
        repo_url = yield from repo_provider(adjustspec, create=False)

        # Non-shallow, but branch-only clone of internal repo
        yield from expect_ok(
            cmd=["git", "clone", "--branch", adjustspec["ref"], "--depth", "1", "--", repo_url.readwrite, d],
            desc="Could not clone with git",
        )
        yield from asgit.setup_commiter(expect_ok, d)

        adjust_type = yield from adjust_provider(d)
        result = yield from commit_adjustments(
            repo_dir=d,
            repo_url=repo_url,
            original_ref=adjustspec["ref"],
            adjust_type=adjust_type,
        )

    return result or {}

#
# Adjust providers
#

def adjust_noop():
    logger.info("Using noop adjust provider")
    @asyncio.coroutine
    def adjust(repo_dir):
        return "NoOp"
    return adjust

def adjust_subprocess(description, cmd):
    logger.info("Using subprocess adjust provider, Description: {description} CMD: {cmd}".format(**locals()))
    log_executable_info(cmd)
    @asyncio.coroutine
    def adjust(repo_dir):
        filled_cmd = [p.format(repo_dir=repo_dir) if p.startswith("{repo_dir}") else p for p in cmd]

        log_context = getattr(asyncio.Task.current_task(), "log_context", "")
        if log_context == "":
            env = None
        else:
            env = {
                "LOG_CONTEXT": asyncio.Task.current_task().log_context,
            }

        logger.info("Executing adjust subprocess")
        # TODO should pipe out stderr and stdout once PME has log-context support
        yield from expect_ok(
            cmd=filled_cmd,
            desc="Alignment subprocess failed",
            cwd=repo_dir,
            env=env,
        )
        return description
    return adjust

#
# Supported
#

provider_types = {
    "noop": adjust_noop,
    "subprocess": adjust_subprocess,
}
