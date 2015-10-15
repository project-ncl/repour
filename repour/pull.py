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

@asyncio.coroutine
def to_internal(internal_repo_url, dirname, origin_ref, origin_url, origin_type):
    # Prepare new repo
    # Note that for orphan branches, we don't need to clone the existing internal repo first
    yield from expect_ok(
        cmd=["git", "-C", dirname, "init"],
        desc="Could not re-init with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", dirname, "remote", "add", "origin", internal_repo_url.readwrite],
        desc="Could not add remote with git",
    )

    yield from asgit.setup_commiter(expect_ok, dirname)
    d = yield from asgit.push_new_dedup_branch(
        expect_ok=expect_ok,
        repo_dir=dirname,
        repo_url=internal_repo_url,
        operation_name="Pull",
        operation_description="""Origin: {origin_url}
Reference: {origin_ref}
Type: {origin_type}
""".format(**locals()),
        orphan=True,
    )
    return d

@asyncio.coroutine
def process_source_tree(pullspec, repo_provider, adjust_provider, repo_dir, origin_type, origin_ref):
    internal_repo_url = yield from repo_provider(pullspec["name"])

    # Process sources into internal branch
    pull_internal = yield from to_internal(internal_repo_url, repo_dir, origin_ref, pullspec["url"], origin_type)

    if pullspec.get("adjust", False):
        adjust_type = yield from adjust_provider(repo_dir)
        adjust_internal = yield from adjust.commit_adjustments(
            repo_dir=repo_dir,
            repo_url=internal_repo_url,
            original_ref=pull_internal["tag"],
            adjust_type=adjust_type,
        )
    else:
        adjust_internal = None

    if adjust_internal is None:
        return pull_internal
    else:
        adjust_internal["pull"] = pull_internal
        return adjust_internal

def _log_scm_success(pullspec):
    msg = "Got {pullspec[type]} tree from {pullspec[url]}".format(**locals())
    if "ref" in pullspec:
        msg += " at ref {pullspec[ref]}".format(**locals())
    logger.info(msg)

#
# Pull operations
#

@asyncio.coroutine
def pull(pullspec, repo_provider, adjust_provider):
    if pullspec["type"] in scm_types:
        internal = yield from scm_types[pullspec["type"]](pullspec, repo_provider, adjust_provider)
    elif pullspec["type"] == archive_type:
        internal = yield from pull_archive(pullspec, repo_provider, adjust_provider)
    else:
        raise exception.PullError("Type '{pullspec[type]}' not supported".format(**locals()))
    return internal

def _simple_scm_pull_function(start, if_ref, end, cleanup=(,)):
    @asyncio.coroutine
    def pull(pullspec, repo_provider, adjust_provider):
        with asutil.TemporaryDirectory(suffix=pullspec["type"]) as clone_dir:
            # Build clone command and failure description
            desc = "Could not clone"
            cmd = start(pullspec, clone_dir)
            if "ref" in pullspec:
                cmd += if_ref(pullspec, clone_dir)
                desc += " ref {pullspec[ref]}".format(**locals())
            cmd += end(pullspec, clone_dir)
            desc += "with {pullspec[type]}".format(**locals())

            # Run clone command
            yield from expect_ok(
                cmd=cmd,
                desc=desc,
            )

            # Cleanup files (ex: .git/)
            for child in cleanup:
                yield from asutil.rmtree(os.path.join(clone_dir, child))

            _log_scm_success(pullspec)

            internal = yield from process_source_tree(
                pullspec=pullspec,
                repo_provider=repo_provider,
                adjust_provider=adjust_provider,
                repo_dir=d,
                origin_type=pullspec["type"],
                origin_ref=pullspec.get("ref", None),
            )

            return internal

    return pull

pull_subversion = _simple_scm_pull_function(
    start=lambda p,d: ["svn", "export"],
    if_ref=lambda p,d: ["--revision", p["ref"]],
    end=lambda p,d: [p["url"], d],
)

pull_mercurial = _simple_scm_pull_function(
    start=lambda p,d: ["hg", "clone"],
    if_ref=lambda p,d: ["--updaterev", p["ref"]],
    end=lambda p,d: [p["url"], d],
    cleanup=[".hg"],
)

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

        internal = yield from process_source_tree(pullspec, repo_provider, adjust_provider, d, "git", pullspec["ref"])

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
                cmd=["bsdtar", "-xf", f.name, "-C", d],
                desc="Could not extract archive with bsdtar",
            )
            # TODO may need to move the files out of an inner dir, but only if single root dir (ex: asd.tar.gz would normally be asd/qwe.txt)

        internal = yield from process_source_tree(pullspec, repo_provider, adjust_provider, d, "archive", archive_filename)

    return internal

#
# Supported
#

scm_types = {
    "git": pull_git,
    "svn": pull_subversion,
    "hg": pull_mercurial,
}
archive_type = "archive"
