import asyncio
import logging
import os
import shutil
import tempfile

from . import asgit
from . import asutil
from . import exception
from .adjust import adjust
from .config import config
from .scm import git_provider

logger = logging.getLogger(__name__)

#
# Utility
#

expect_ok = asutil.expect_ok_closure(exception.PullCommandError)

git = git_provider.git_provider()


@asyncio.coroutine
def to_internal(internal_repo_url, dirname, origin_ref, origin_url, origin_type):
    # Prepare new repo
    # Note that for orphan branches, we don't need to clone the existing internal repo first

    c = yield from config.get_configuration()
    git_user = c.get("git_username")
    yield from git["init"](dirname)
    yield from git["add_remote"](dirname, "origin", asutil.add_username_url(internal_repo_url.readwrite, git_user))

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
        adjust_type = yield from adjust_provider(pullspec, repo_dir)
        # TODO This does not look good, use code in adjust to commit adjustments
        adjust_internal = yield from adjust.commit_adjustments(
            repo_dir=repo_dir,
            repo_url=internal_repo_url,
            original_ref=pull_internal["tag"],
            adjust_type=adjust_type,
            force_continue_on_no_changes=True,
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
def pull(pullspec, repo_provider):
    if pullspec["type"] in scm_types:
        internal = yield from scm_types[pullspec["type"]](pullspec, repo_provider, adjust.adjust)
    elif pullspec["type"] == archive_type:
        internal = yield from pull_archive(pullspec, repo_provider, adjust.adjust)
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
def extract(filePath, targetDirPath):
    fileType = yield from expect_ok(
        cmd=["file", filePath],
        desc="Could not get file type with 'file'.",
        stdout=asutil.process_stdout_options["text"]
    )

    # Supported: zip, tar, and tar.gz
    if "Zip" in fileType:
        yield from expect_ok(
            cmd=["unzip", filePath, "-d", targetDirPath],
            desc="Could not extract zip (?) archive with 'unzip'. "
                 + "Type of file '" + filePath + "' was detected as '" + fileType + "'.",
        )
    elif "gzip" in fileType:  # expect tar.gz, not just gz
        yield from expect_ok(
            cmd=["tar", "-xzf", filePath, "-C", targetDirPath],
            desc="Could not extract tar.gz (?) archive with 'tar'. "
                 + "Type of file '" + filePath + "' was detected as '" + fileType + "'.",
        )
    elif "tar" in fileType:  # tar
        yield from expect_ok(
            cmd=["tar", "-xf", filePath, "-C", targetDirPath],
            desc="Could not extract tar (?) archive with 'tar'. "
                 + "Type of file '" + filePath + "' was detected as '" + fileType + "'.",
        )
    else:
        raise Exception("Unable to extract the archive. Supported are: zip, tar and tar+gz."
                        + "Type of file '" + filePath + "' was detected as '" + fileType + "'.")


@asyncio.coroutine
def pull_archive(pullspec, repo_provider, adjust_provider):
    with asutil.TemporaryDirectory(suffix="extract") as extract_dir:
        with tempfile.NamedTemporaryFile(suffix="archive") as archive_file:
            # Download archive into stream
            logger.info("Downloading {pullspec[url]}...".format(**locals()))
            archive_filename = yield from asutil.download(pullspec["url"], archive_file)
            logger.info("Got archive tree from {pullspec[url]} named {archive_filename}".format(**locals()))

            yield from extract(archive_file.name, extract_dir)

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
