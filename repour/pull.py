import asyncio
import collections
import datetime
import logging
import os
import socket
import tempfile
import urllib.parse

from . import asutil
from . import adjust
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
    tag_refspec_pattern = "refs/tags/{origin_ref}_*_root".format(**locals())

    commit_message = """Origin: {origin_url}
Reference: {origin_ref}
Type: {origin_type}
""".format(**locals())

    # Prepare new repo
    # Note that for orphan branches, we don't need to clone the existing internal repo first
    yield from expect_ok(
        cmd=["git", "-C", dirname, "init"],
        desc="Could not re-init with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "remote", "add", "origin", internal_repo_url],
        desc="Could not add remote with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "config", "--local", "user.name", "Repour"],
        desc="Could not set commiter name with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "config", "--local", "user.email", "<repour@{}>".format(socket.getfqdn())],
        desc="Could not set commiter email with git",
    )

    # Prepare orphaned branch with root commit
    yield from expect_ok(
        cmd=["git", "-C", dirname, "checkout", "--orphan", branch_name],
        desc="Could not create branch with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "add", "-A"],
        desc="Could not add files with git",
    )
    # To maintain an identical commitid for identical trees, use a fixed author/commit date.
    commit_date="1970-01-01 00:00:00 +0000"
    yield from expect_ok(
        cmd=["git", "-C", dirname, "commit", "-m", commit_message],
        desc="Could not commit files with git",
        env={
            "GIT_AUTHOR_DATE": commit_date,
            "GIT_COMMITTER_DATE": commit_date,
        },
    )

    # Check if any root tag in the internal repo matches the commitid we currently have.
    # Note that this operation isn't atomic, but it won't matter too much if interleaving happens.
    # Worst case, you'll have multiple branch/root_tag pairs pointing at the same commit.
    head_commitid = yield from expect_ok(
        cmd=["git", "-C", dirname, "rev-parse", "HEAD"],
        desc="Could not get HEAD commitid with git",
        stdout="single",
    )
    stdout_lines = yield from expect_ok(
        cmd=["git", "ls-remote", internal_repo_url, tag_refspec_pattern],
        desc="Could not read remote refs with git",
        stdout="lines",
    )
    for l in stdout_lines:
        commit_id, refspec = l.split("\t")
        if commit_id == head_commitid:
            # ex: refs/tags/proj-1.0_1436360795_root -> proj-1.0_1436360795_root
            existing_tag = refspec.split("/", 2)[-1]
            break
    else:
        existing_tag = None

    if existing_tag is None:
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

    # Discard cloned branch and use existing branch and tag
    else:
        # ex: proj-1.0_1436360795_root -> proj-1.0_1436360795
        existing_branch = existing_tag[:-5]

        logger.info("Using existing branch {branch_name} in internal repo {internal_repo_url}".format(**locals()))

        return {
            "branch": existing_branch,
            "tag": existing_tag,
            "url": internal_repo_url,
        }

#
# Pull operations
#

@asyncio.coroutine
def pull(pullspec, repo_provider, adjust_provider):
    if pullspec["type"] in scm_types:
        internal = yield from scm_types[pullspec["type"]](pullspec, repo_provider, adjust_provider)
    elif pullspec["type"] == archive_type:
        internal = yield from pull_archive(repo_provider, pullspec, adjust_provider)
    else:
        raise exception.PullError("Type '{pullspec[type]}' not supported".format(**locals()))
    return internal

@asyncio.coroutine
def pull_git(pullspec, repo_provider, adjust_provider):
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

        if pullspec.get("adjust", False):
            adjust_provider(d)
            adjust.commit_adjustments(internal_repo_url, d)

    return internal

@asyncio.coroutine
def pull_archive(pullspec, repo_provider, adjust_provider):
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
            # TODO may need to move the files out of an inner dir, but only if single root dir (ex: asd.tar.gz would normally be asd/qwe.txt)

        # TODO create internal repo concurrently?
        internal_repo_url = yield from repo_provider(pullspec["name"])

        # Process sources into internal branch
        internal = yield from to_internal(internal_repo_url, d, archive_filename, pullspec["url"], "archive")

        if pullspec.get("adjust", False):
            adjust_provider(d)
            adjust.commit_adjustments(internal_repo_url, d)

    return internal

#
# Supported
#

scm_types = {"git": pull_git}
archive_type = "archive"
