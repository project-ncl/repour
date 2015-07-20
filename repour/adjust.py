import asyncio

from . import asutil
from . import exception

logger = logging.getLogger(__name__)

#
# Utility
#

expect_ok = asutil.expect_ok_closure(exception.AdjustCommandError)

#
# Atomic adjust operation
#

@asyncio.coroutine
def adjust(adjustspec, adjust_provider):
    # TODO new clone

    yield from adjust_command(adjustspec)

    # TODO add/commit/push

    return {
        "branch": "", # TODO
        "tag": "", # TODO
    }

#
# Adjust providers
#

@asyncio.coroutine
def adjust_noop():
    pass

@asyncio.coroutine
def adjust_subprocess(cmd):
    pass

#
# Supported
#

provider_types = {
    "noop": adjust_noop,
    "subprocess": adjust_subprocess,
}
