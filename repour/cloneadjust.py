import asyncio
import logging
import os

from . import asutil
from . import exception
from .adjust import adjust
from .scm import git_provider

logger = logging.getLogger(__name__)

#
# Utility
#

expect_ok = asutil.expect_ok_closure(exception.CommandError)

git = git_provider.git_provider()

@asyncio.coroutine
def cloneadjust(clonespec, repo_provider):
    if clonespec["type"] in scm_types:
        internal = yield from scm_types[clonespec["type"]](clonespec, repo_provider, adjust.adjust)
    else:
        raise exception.CloneError("Type '{clonespec[type]}' not supported for 'clone' operation.".format(**locals()))

    return internal


@asyncio.coroutine
def clone_adjust_git(clonespec, repo_provider, adjust_provider):
    with asutil.TemporaryDirectory(suffix="git") as clone_dir:

        internal_repo_url = yield from repo_provider(clonespec)
        yield from git["clone"](clone_dir, clonespec["originRepoUrl"])  # Clone origin
        yield from git["checkout"](clone_dir, clonespec["ref"])  # Checkout ref
        yield from git["add_remote"](clone_dir, "target", internal_repo_url.readwrite)  # Add target remote

        ref = clonespec["ref"]

        isRefBranch = yield from git["is_branch"](clone_dir, ref)  # if ref is a branch, we don't have to create one
        isRefTag = yield from git["is_tag"](clone_dir, ref)

        if isRefBranch:
            yield from git["push"](clone_dir, "target", ref)  # push it to the remote
        elif isRefTag:
            yield from git["push_with_tags"](clone_dir, ref, remote="target")
        else:
            # Case if ref is a particular SHA
            # We can't really push a particular hash to the target repository
            # unless it is in a branch. We have to create the branch to be able
            # to push the SHA
            branch = "branch-" + ref
            yield from git["add_branch"](clone_dir, branch)
            yield from git["push"](clone_dir, "target", branch)  # push it to the remote

        do_adjust = clonespec.get("adjust", False)
        adjust_param = clonespec.get("adjustParameters", False)

        if do_adjust:
            # TODO: this re-clones the repository to run PME, there must be a
            #       better way
            adjust_type = yield from adjust_provider(clonespec, repo_provider)

            clonespec["adjust_result"] = adjust_type
        else:
            clonespec["adjust_result"] = None

        return clonespec

scm_types = {
    "git": clone_adjust_git,
}

