import asyncio
import logging
import os

from . import asutil
from . import exception

logger = logging.getLogger(__name__)

#
# Utility
#

expect_ok = asutil.expect_ok_closure(exception.CommandError)

@asyncio.coroutine
def clone(clonespec, repo_provider, adjust_provider):
    if clonespec["type"] in scm_types:
        internal = yield from scm_types[clonespec["type"]](clonespec)
    else:
        raise exception.CloneError("Type '{clonespec[type]}' not supported for 'clone' operation.".format(**locals()))
    return internal


@asyncio.coroutine
def clone_git(clonespec):
    with asutil.TemporaryDirectory(suffix="git") as clone_dir:

        @asyncio.coroutine
        def git_clone(originRepoUrl):
            yield from expect_ok(
                cmd=["git", "clone", "--", originRepoUrl, clone_dir],
                desc="Could not clone {} with git.".format(originRepoUrl),
            )

        @asyncio.coroutine
        def git_checkout(ref):
            yield from expect_ok(
                cmd=["git", "-C", clone_dir, "checkout", ref, "--"],
                desc="Could not checkout ref {} with git.".format(ref),
            )

        @asyncio.coroutine
        def git_add_remote(name, url):
            yield from expect_ok(
                cmd=["git", "-C", clone_dir, "remote", "add", name, url, "--"],
                desc="Could not add remote {} with git.".format(url),
            )

        @asyncio.coroutine
        def git_is_branch(ref):
            try:  # TODO improve, its ugly
                yield from expect_ok(
                    cmd=["git", "-C", clone_dir, "show-ref", "--quiet", "--heads", ref, "--"],
                    desc="Ignore this.",
                )
                return True
            except Exception as e:
                return False

        @asyncio.coroutine
        def git_add_branch(name):
            yield from expect_ok(
                cmd=["git", "-C", clone_dir, "branch", name, "--"],
                desc="Could not add branch {} with git.".format(name),
            )

        @asyncio.coroutine
        def git_push(remote, branch):  # Warning! --force
            yield from expect_ok(
                cmd=["git", "-C", clone_dir, "push", "--force", remote, branch, "--"],
                desc="Could not (force) push branch '{}' to remote '{}' with git".format(branch, remote),
            )

        yield from git_clone(clonespec["originRepoUrl"])  # Clone origin
        yield from git_checkout(clonespec["ref"])  # Checkout ref
        yield from git_add_remote("target", clonespec["targetRepoUrl"])  # Add target remote
        branch = clonespec["ref"]
        isRefBranch = yield from git_is_branch(branch)  # if ref is a branch, we don't have to create one
        if not isRefBranch:
            branch = "branch-" + branch
            yield from git_add_branch(branch)
        yield from git_push("target", branch)  # push it to the remote
        clonespec["ref"] = branch
        return clonespec

scm_types = {
    "git": clone_git,
}

