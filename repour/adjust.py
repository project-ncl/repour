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
    # TODO add/commit/push

    # TODO what is the best way to identify the new commit?
    return {
        "branch": "",
        "tag": "",
    }

#
# Adjust operation
#

@asyncio.coroutine
def adjust(adjustspec, adjust_provider):
    # TODO new clone
    repo_dir = None

    yield from adjust_provider(repo_dir)

    result = yield from commit_adjustments(repo_dir)

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
