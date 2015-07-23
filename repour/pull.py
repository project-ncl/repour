import asyncio
import collections
import datetime
import logging
import os
import tempfile
import urllib.parse

from . import asgit
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
    # There are a few priorities for reference names:
    #   - Amount of information in the name itself
    #   - Length
    #   - Parsability
    # The following scheme does not include the origin_ref, although it is good
    # information, because it comprimises length and parsability too much.

    timestamp = unix_time()
    branch_name = "pull-{timestamp}".format(**locals())
    tag_name = "{branch_name}-root".format(**locals())
    tag_refspec_pattern = "refs/tags/pull-*-root".format(**locals())

    tag_message = """Origin: {origin_url}
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
    yield from asgit.setup_commiter(expect_ok, dirname)

    # Prepare orphaned branch with root commit
    yield from asgit.prepare_new_branch(expect_ok, dirname, branch_name, orphan=True)
    # For maximum tree deduplication, the commit message should be fixed
    yield from asgit.fixed_date_commit(expect_ok, dirname, "Pull")

    # Check if any root tag in the internal repo matches the commitid we currently have.
    # Note that this operation isn't atomic, but it won't matter too much if interleaving happens.
    # Worst case, you'll have multiple branch/root_tag pairs pointing at the same commit.
    existing_tag = yield from asgit.deduplicate_head_tag(expect_ok, dirname, tag_refspec_pattern)

    if existing_tag is None:
        yield from asgit.annotated_tag(expect_ok, dirname, tag_name, tag_message)
        yield from asgit.push_with_tags(expect_ok, dirname, branch_name)

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

        # Have to be careful about this state if anything reuses the repo.
        # In the adjust scenario, the new branch it creates (from an identical
        # commitid) will isolate it from the discarded local branches.

        logger.info("Using existing branch {branch_name} in internal repo {internal_repo_url}".format(**locals()))

        return {
            "branch": existing_branch,
            "tag": existing_tag,
            "url": internal_repo_url,
        }

@asyncio.coroutine
def process_source_tree(pullspec, repo_provider, adjust_provider, repo_dir, origin_type):
    internal_repo_url = yield from repo_provider(pullspec["name"])

    # Process sources into internal branch
    pull_internal = yield from to_internal(internal_repo_url, repo_dir, pullspec["ref"], pullspec["url"], origin_type)

    if pullspec.get("adjust", False):
        yield from adjust_provider(repo_dir)
        # TODO must give pull_internal tag name to commit_adjustments to handle discard scenario
        adjust_internal = yield from adjust.commit_adjustments(internal_repo_url, repo_dir)
    else:
        adjust_internal = None

    return adjust_internal or pull_internal

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
            cmd=["git", "clone", "--branch", pullspec["ref"], "--depth", "1", "--", pullspec["url"], d],
            desc="Could not clone with git",
        )
        # Clean up git metadata
        yield from asutil.rmtree(os.path.join(d, ".git"))
        logger.info("Got git tree from {pullspec[url]} at ref {pullspec[ref]}".format(**locals()))

        internal = yield from process_source_tree(pullspec, repo_provider, adjust_provider, d, "git")

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

        internal = yield from process_source_tree(pullspec, repo_provider, adjust_provider, d, "archive")

    return internal

#
# Supported
#

scm_types = {"git": pull_git}
archive_type = "archive"
