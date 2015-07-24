import asyncio
import logging

from . import asgit
from . import asutil
from . import exception

logger = logging.getLogger(__name__)

#
# Utility
#

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
        repo_url = yield from repo_provider(adjustspec["name"], create=False)

        # Non-shallow, but branch-only clone of internal repo
        yield from expect_ok(
            cmd=["git", "clone", "--branch", adjustspec["ref"], "--", repo_url, d],
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

    return result

#
# Adjust providers
#

def adjust_noop():
    @asyncio.coroutine
    def adjust(repo_dir):
        return "NoOp"
    return adjust

@asyncio.coroutine
def adjust_subprocess(description, cmd):
    @asyncio.coroutine
    def adjust(repo_dir):
        filled_cmd = [repo_dir if p == "{repo_dir}" else p for p in cmd]
        yield from expect_ok(filled_cmd, "Alignment subprocess failed")
        return description
    return adjust

#
# Supported
#

provider_types = {
    "noop": adjust_noop,
    "subprocess": adjust_subprocess,
}
