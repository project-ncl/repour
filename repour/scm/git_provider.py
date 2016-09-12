import asyncio
import logging
import os

from .. import asutil
from .. import exception

logger = logging.getLogger(__name__)

expect_ok = asutil.expect_ok_closure(exception.CommandError)

#
# Collection of all required SCM commands in one place.
# The same method names are expected to be implemented by other providers.
#

def git_provider():
    @asyncio.coroutine
    def clone_deep(dir, url):
        yield from expect_ok(
            cmd=["git", "clone", "--", url, dir],
            desc="Could not clone with git"
        )

    @asyncio.coroutine
    def checkout(dir, ref):
        # Checkout tag or branch or commit-id
        yield from expect_ok(
            cmd=["git", "-C", dir, "checkout", ref, "--"],
            desc="Could not checkout ref {ref} from clone of {url} with git".format(**locals()),
        )

    @asyncio.coroutine
    def clone_checkout_branch_tag_shallow(dir, url, branch_or_tag):
        yield from expect_ok(
            cmd=["git", "clone", "--branch", branch_or_tag, "--depth", "1", "--", url, dir],
            desc="Could not clone with git",
            stderr=None,
        )

    @asyncio.coroutine
    def clone_checkout_branch_tag_deep(dir, url, branch_or_tag):
        yield from expect_ok(
            cmd=["git", "clone", "--branch", branch_or_tag, "--", url, dir],
            desc="Could not clone with git",
            stderr=None,
        )

    @asyncio.coroutine
    def clone_checkout_ref_auto(dir, url, ref):
        """
        Clone and checkout ref as shallowly as possible
        """
        try:
            yield from clone_checkout_branch_tag_shallow(dir, url, ref)
        except exception.CommandError as e:
            if "does not support" in e.stderr:
                # Fallback to single branch (for dumb http transport)
                try:
                    yield from clone_checkout_branch_tag_deep(dir, url, ref)
                except exception.CommandError as e:
                    # Fallback to deep+checkout (for commitid)
                    if "not found" in e.stderr:
                        yield from clone_deep(dir, url)
                        yield from checkout(dir, ref)
                    else:
                        raise
            elif "not found" in e.stderr:
                # Fallback to deep+checkout (for commitid)
                yield from clone_deep(dir, url)
                yield from checkout(dir, ref)
            else:
                raise

    @asyncio.coroutine
    def cleanup(dir):
        yield from asutil.rmtree(os.path.join(dir, ".git"))

    return {
        "clone_deep": clone_deep,
        "checkout": checkout,
        "clone_checkout_branch_tag_shallow": clone_checkout_branch_tag_shallow,
        "clone_checkout_branch_tag_deep": clone_checkout_branch_tag_deep,
        "clone_checkout_ref_auto": clone_checkout_ref_auto,
        "cleanup": cleanup
    }
