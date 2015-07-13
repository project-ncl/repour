import asyncio
import collections
import datetime
import logging
import os
import socket
import tempfile
import urllib.parse

from . import asutil
from . import exception

logger = logging.getLogger(__name__)

#
# Utility
#

expect_ok = asutil.expect_ok_closure(exception.PullCommandError)

def unix_time(now=None):
    now = datetime.datetime.utcnow() if now is None else now
    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = now - epoch
    return round(delta.total_seconds())

@asyncio.coroutine
def to_internal(internal_repo_url, dirname, origin_ref, origin_url, origin_type):
    timestamp = unix_time()

    branch_name = "{origin_ref}_{timestamp}".format(**locals())
    tag_name = "{origin_ref}_{timestamp}_root".format(**locals())

    commit_message = """Origin: {origin_url}
Reference: {origin_ref}
Type: {origin_type}
""".format(**locals())

    yield from expect_ok(
        cmd=["git", "-C", dirname, "init"],
        desc="Could not re-init with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "remote", "add", "origin", internal_repo_url],
        desc="Could not add remote with git",
    )

    # TODO gpg signing of commit and tag https://git-scm.com/book/tr/v2/Git-Tools-Signing-Your-Work

    # Commit onto orphaned branch and push
    yield from expect_ok(
        cmd=["git", "-C", dirname, "checkout", "--orphan", branch_name],
        desc="Could not create branch with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "config", "--local", "user.name", "Repour"],
        desc="Could not set commiter name with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "config", "--local", "user.email", "<repour@{}>".format(socket.getfqdn())],
        desc="Could not set commiter email with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "add", "-A"],
        desc="Could not add files with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "commit", "-m", commit_message],
        desc="Could not commit files with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "push", "origin", branch_name],
        desc="Could not push branch with git",
    )

    # Tag the branch root and push
    yield from expect_ok(
        cmd=["git", "-C", dirname, "tag", tag_name],
        desc="Could not add tag with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "push", "origin", "--tags"],
        desc="Could not push tag with git",
    )

    logger.info("Pushed branch {branch_name} to internal repo {internal_repo_url}".format(**locals()))

    return {
        "branch": branch_name,
        "tag": tag_name,
        "url": internal_repo_url,
    }

#
# Pull operations
#

@asyncio.coroutine
def pull(pullspec, repo_provider):
    if pullspec["type"] in scm_types:
        internal = yield from scm_types[pullspec["type"]](pullspec, repo_provider)
    elif pullspec["type"] == archive_type:
        internal = yield from pull_archive(repo_provider, pullspec)
    else:
        raise exception.PullError("Type '{pullspec[type]}' not supported".format(**locals()))
    return internal

@asyncio.coroutine
def pull_git(pullspec, repo_provider):
    with asutil.TemporaryDirectory(suffix="git") as d:
        # Shallow clone of the git ref (tag or branch)
        yield from expect_ok(
            cmd=["git", "clone", "--branch", pullspec["tag"], "--depth", "1", "--", pullspec["url"], d],
            desc="Could not clone with git",
        )
        # Clean up git metadata
        yield from asutil.rmtree(os.path.join(d, ".git"))
        logger.info("Got git tree from {pullspec[url]} at tag {pullspec[tag]}".format(**locals()))

        # TODO create internal repo concurrently?
        internal_repo_url = yield from repo_provider(pullspec["name"])

        # Process sources into internal branch
        internal = yield from to_internal(internal_repo_url, d, pullspec["tag"], pullspec["url"], "git")

    return internal

@asyncio.coroutine
def pull_archive(pullspec, repo_provider):
    with asutil.TemporaryDirectory(suffix="extract") as d:
        with tempfile.NamedTemporaryFile(suffix="archive") as f:
            # Download archive into stream
            archive_filename = yield from asutil.download(pullspec["url"], f)
            logger.info("Got archive tree from {pullspec[url]} named {archive_filename}".format(**locals()))

            # Use libarchive/bsdtar to extract into temp dir
            yield from expect_ok(
                cmd=["bsdtar", "-xf", f.name, "-C", d, "--chroot"],
                desc="Could not extract archive with bsdtar",
            )

        # TODO create internal repo concurrently?
        internal_repo_url = yield from repo_provider(pullspec["name"])

        # Process sources into internal branch
        internal = yield from to_internal(internal_repo_url, d, archive_filename, pullspec["url"], "archive")

    return internal

#
# Supported
#

scm_types = {"git": pull_git}
archive_type = "archive"
