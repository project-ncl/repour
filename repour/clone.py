import asyncio
import logging
import os

from . import asutil
from . import exception
from .config import config
from .scm import git_provider

logger = logging.getLogger(__name__)

#
# Utility
#

expect_ok = asutil.expect_ok_closure(exception.CommandError)

git = git_provider.git_provider()

@asyncio.coroutine
def push_sync_changes(work_dir, ref, remote="origin"):
    """ This function is used when we want to sync a repository with another one
        It assumes that you have already set the remote to be the 'other' repository

        If the ref is a tag, the tag is pushed to the remote
        If the ref is a branch, the branch, and its changes, are pushed to the remote
        If the ref is a SHA, the SHA is pushed to the remote indirectly via the creation of a tag

        Parameters:
        - work_dir: :str: location of git repository
        - ref: Git ref to sync
        - remote: remote to push the ref to
    """

    isRefBranch = yield from git["is_branch"](work_dir, ref)  # if ref is a branch, we don't have to create one
    isRefTag = yield from git["is_tag"](work_dir, ref)

    if isRefBranch:
        yield from git["push"](work_dir, remote, ref)  # push it to the remote
    elif isRefTag:
        c = yield from config.get_configuration()
        git_user = c.get("git_username")

        yield from git["push_with_tags"](work_dir, ref, git_user, remote=remote)
    else:
        # Case if ref is a particular SHA
        # We can't really push a particular hash to the target repository
        # unless it is a tag. We have to create the tag to be able
        # to push the SHA
        tag_name = "repour-sync-" + ref

        tag_already_exists = yield from git["is_tag"](work_dir, ref)

        if not tag_already_exists:
            yield from git["add_tag"](work_dir, tag_name)
            yield from git["push"](work_dir, remote, tag_name)
        else:
            logger.info("Tag already exists in internal repository. Not pushing anything")

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

        c = yield from config.get_configuration()
        git_user = c.get("git_username")

        if "ref" in clonespec and clonespec["ref"]:
            yield from git["clone"](clone_dir, clonespec["originRepoUrl"])  # Clone origin
            yield from git["checkout"](clone_dir, clonespec["ref"], force=True)  # Checkout ref
            yield from git["add_remote"](clone_dir, "target", asutil.add_username_url(clonespec["targetRepoUrl"], git_user))  # Add target remote

            ref = clonespec["ref"]
            yield from push_sync_changes(clone_dir, ref, "target")
        else:
            # Sync everything if ref not specified
            # From: https://stackoverflow.com/a/7216269/2907906
            logger.info("Syncing everything")
            yield from git["clone_mirror"](clone_dir + "/.git", clonespec["originRepoUrl"])  # Clone origin
            yield from git["disable_bare_repository"](clone_dir)
            yield from git["reset_hard"](clone_dir)
            yield from git["add_remote"](clone_dir, "target", asutil.add_username_url(clonespec["targetRepoUrl"], git_user))  # Add target remote
            yield from git["push_all"](clone_dir, "target", tags_also=True)

        return clonespec

scm_types = {
    "git": clone_git,
}
