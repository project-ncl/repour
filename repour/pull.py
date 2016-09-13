import asyncio
import logging
import os
import shutil
import tempfile

from .scm import git_provider
from . import adjust
from . import asgit
from . import asutil
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
    internal_repo_url = yield from repo_provider(pullspec)

    # Process sources into internal branch
    pull_internal = yield from to_internal(internal_repo_url, repo_dir, origin_ref, pullspec["url"], origin_type)

    do_adjust = pullspec.get("adjust", False)
    if do_adjust:
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
        if do_adjust:
            # adjust_internal is None with do_adjust means adjust made no changes
            pull_internal["pull"] = pull_internal.copy()
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

def _simple_scm_pull_function(start, if_ref, end, cleanup=[]):
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
            desc += " with {pullspec[type]}".format(**locals())

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
                repo_dir=clone_dir,
                origin_type=pullspec["type"],
                origin_ref=pullspec.get("ref", None),
            )

            return internal

    return pull

pull_subversion = _simple_scm_pull_function(
    start=lambda p,d: ["svn", "export", "--force"],
    if_ref=lambda p,d: ["--revision", p["ref"]],
    end=lambda p,d: [p["url"], d],
)

pull_mercurial = _simple_scm_pull_function(
    start=lambda p,d: ["hg", "clone"],
    if_ref=lambda p,d: ["--updaterev", p["ref"]],
    end=lambda p,d: [p["url"], d],
    cleanup=[".hg"],
)

git = git_provider.git_provider()


@asyncio.coroutine
def pull_git(pullspec, repo_provider, adjust_provider):
    with asutil.TemporaryDirectory(suffix="git") as clone_dir:

        if "ref" in pullspec:
            yield from git["clone_checkout_ref_auto"](clone_dir, pullspec["url"], pullspec["ref"])
        else:
            # No ref, use HEAD/default
            yield from git["clone_deep"](clone_dir, pullspec["url"])

        # Clean up metadata
        yield from git["cleanup"](clone_dir)
        _log_scm_success(pullspec)

        internal = yield from process_source_tree(
            pullspec=pullspec,
            repo_provider=repo_provider,
            adjust_provider=adjust_provider,
            repo_dir=clone_dir,
            origin_type=pullspec["type"],
            origin_ref=pullspec.get("ref", None),
        )

    return internal

@asyncio.coroutine
def pull_archive(pullspec, repo_provider, adjust_provider):
    with asutil.TemporaryDirectory(suffix="extract") as extract_dir:
        with tempfile.NamedTemporaryFile(suffix="archive") as archive_file:
            # Download archive into stream
            archive_filename = yield from asutil.download(pullspec["url"], archive_file)
            logger.info("Got archive tree from {pullspec[url]} named {archive_filename}".format(**locals()))

            # Use libarchive/bsdtar to extract into temp dir
            yield from expect_ok(
                cmd=["bsdtar", "-xf", archive_file.name, "-C", extract_dir],
                desc="Could not extract archive with bsdtar",
            )

        # Determine if there is a single inner root dir, as is common with archive files
        entry_count = 0
        for entry in os.listdir(extract_dir):
            if not os.path.isdir(os.path.join(extract_dir, entry)) or entry_count > 0:
                shuck = None
                break
            entry_count += 1
        else:
            shuck = os.path.join(extract_dir, entry)

        @asyncio.coroutine
        def process(process_dir):
            internal = yield from process_source_tree(
                pullspec=pullspec,
                repo_provider=repo_provider,
                adjust_provider=adjust_provider,
                repo_dir=process_dir,
                origin_type=pullspec["type"],
                origin_ref=archive_filename,
            )
            return internal

        if shuck is None:
            internal = yield from process(extract_dir)
            return internal
        else:
            # To avoid any possiblity of a name collision between the inner dir
            # and its contents, create a new tempdir and move them there
            with asutil.TemporaryDirectory(suffix="archive") as repo_dir:
                # Move the contents of the inner dir
                for entry in os.listdir(shuck):
                    shutil.move(os.path.join(shuck, entry), repo_dir)
                internal = yield from process(repo_dir)
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
