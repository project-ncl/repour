import asyncio
import logging
import os

from . import asutil
from . import exception
from .scm import git_provider

logger = logging.getLogger(__name__)

#
# Utility
#

expect_ok = asutil.expect_ok_closure(exception.CommandError)

git = git_provider.git_provider()

@asyncio.coroutine
def clone(clonespec, repo_provider):
    if clonespec["type"] in scm_types:
        internal = yield from scm_types[clonespec["type"]](clonespec)
    else:
        raise exception.CloneError("Type '{clonespec[type]}' not supported for 'clone' operation.".format(**locals()))
    return internal


@asyncio.coroutine
def clone_git(clonespec):
    with asutil.TemporaryDirectory(suffix="git") as clone_dir:

        yield from git["clone"](clone_dir, clonespec["originRepoUrl"])  # Clone origin
        yield from git["checkout"](clone_dir, clonespec["ref"])  # Checkout ref
        yield from git["add_remote"](clone_dir, "target", clonespec["targetRepoUrl"])  # Add target remote
        branch = clonespec["ref"]
        isRefBranch = yield from git["is_branch"](clone_dir, branch)  # if ref is a branch, we don't have to create one
        if not isRefBranch:
            branch = "branch-" + branch
            yield from git["add_branch"](clone_dir, branch)
        yield from git["push_force"](clone_dir, "target", branch)  # push it to the remote
        clonespec["ref"] = branch
        return clonespec

scm_types = {
    "git": clone_git,
}

