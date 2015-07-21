import asyncio
import logging

from . import asutil
from . import exception

logger = logging.getLogger(__name__)

#
# Utility
#

expect_ok = asutil.expect_ok_closure(exception.AdjustCommandError)

@asyncio.coroutine
def commit_adjustments(repo_url, repo_dir):
    branch_name = TODO
    tag_name = TODO
    commit_message = TODO

    expect_ok(
        cmd=["git", "-C", dirname, "add", "-A"],
        desc="Could not add files with git",
    )

    expect_ok(
        cmd=["git", "-C", dirname, "checkout", "-b", branch_name],
        desc="Could not add files with git",
    )

    try:
        expect_ok(
            cmd=["git", "-C", dirname, "commit", "-m", commit_message],
            desc="Could not commit files with git",
        )
    except exception.AdjustCommandError as e:
        if e.exit_code == 1:
            # No changes were made
            return None
        else:
            raise
    else:
        yield from expect_ok(
            cmd=["git", "-C", dirname, "push", "origin", branch_name],
            desc="Could not push branch with git",
        )
        yield from expect_ok(
            cmd=["git", "-C", dirname, "tag", tag_name],
            desc="Could not add tag with git",
        )
        yield from expect_ok(
            cmd=["git", "-C", dirname, "push", "origin", "--tags"],
            desc="Could not push tag with git",
        )

        return {
            "branch": branch_name,
            "tag": tag_name,
            "url": repo_url,
        }

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

        yield from adjust_provider(d)

        result = yield from commit_adjustments(d)

    return result

#
# Adjust providers
#

def adjust_noop():
    @asyncio.coroutine
    def adjust(repo_dir):
        pass
    return adjust

@asyncio.coroutine
def adjust_subprocess(cmd):
    @asyncio.coroutine
    def adjust(repo_dir):
        filled_cmd = [repo_dir if p == "{repo_dir}" else p for p in cmd]
        yield from expect_ok(filled_cmd, "Alignment subprocess failed")
    return adjust

#
# Supported
#

provider_types = {
    "noop": adjust_noop,
    "subprocess": adjust_subprocess,
}
