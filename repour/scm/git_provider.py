import asyncio
import logging
import os
import re

from .. import asutil
from .. import exception

logger = logging.getLogger(__name__)

expect_ok = asutil.expect_ok_closure(exception.CommandError)


#
# Collection of all required SCM commands in one place.
# The same method names are expected to be implemented by other providers.
#

def git_provider():
    @asyncio.coroutine
    def clone_deep(dir, url):
        yield from expect_ok(
            cmd=["git", "clone", "--", url, dir],
            desc="Could not clone with git"
        )

    @asyncio.coroutine
    def checkout(dir, ref):
        # Checkout tag or branch or commit-id
        yield from expect_ok(
            cmd=["git", "checkout", ref],
            cwd=dir,
            desc="Could not checkout ref {ref} with git".format(**locals()),
        )

    @asyncio.coroutine
    def clone_checkout_branch_tag_shallow(dir, url, branch_or_tag):
        yield from expect_ok(
            cmd=["git", "clone", "--branch", branch_or_tag, "--depth", "1", "--", url, dir],
            desc="Could not clone with git",
            stderr=None,
        )

    @asyncio.coroutine
    def clone_checkout_branch_tag_deep(dir, url, branch_or_tag):
        yield from expect_ok(
            cmd=["git", "clone", "--branch", branch_or_tag, "--", url, dir],
            desc="Could not clone with git",
            stderr=None,
        )

    @asyncio.coroutine
    def clone(dir, url):
        yield from expect_ok(
            cmd=["git", "clone", "--", url, dir],
            desc="Could not clone {} with git.".format(url),
        )

    @asyncio.coroutine
    def add_remote(dir, name, url):
        yield from expect_ok(
            cmd=["git", "remote", "add", name, url, "--"],
            cwd=dir,
            desc="Could not add remote {} with git.".format(url),
        )

    @asyncio.coroutine
    def is_branch(dir, ref):
        try:  # TODO improve, its ugly
            yield from expect_ok(
                cmd=["git", "show-ref", "--quiet", "--heads", ref, "--"],
                cwd=dir,
                desc="Ignore this.",
            )
            return True
        except Exception as e:
            return False

    @asyncio.coroutine
    def add_branch(dir, name):
        yield from expect_ok(
            cmd=["git", "branch", name, "--"],
            cwd=dir,
            desc="Could not add branch {} with git.".format(name),
        )

    @asyncio.coroutine
    def push_force(dir, remote, branch):  # Warning! --force
        yield from expect_ok(
            cmd=["git", "push", "--force", remote, branch, "--"],
            cwd=dir,
            desc="Could not (force) push branch '{}' to remote '{}' with git".format(branch, remote),
        )

    @asyncio.coroutine  # TODO merge with above
    def push_with_tags(dir, branch, remote="origin", tryAtomic=True):
        """
        Warning: Atomic push is supported since git version 2.4.
        If the atomic push is not supported by git client OR repository provider,
        this method re-tries without it and returns false.
        If an exception is thrown, some other error occurred and push did not
        succeed.

        If branch is None, it is assumed that you only want to push the tags
        """

        def do(atomic):
            if branch is None:
                options = ["--tags"]
                failure_push_msg = "tag"
            else:
                options = ["--follow-tags", remote, branch]
                failure_push_msg = "tag+branch"

            yield from expect_ok(
                cmd=["git", "push"] + (["--atomic"] if atomic else []) + options,
                desc="Could not" + (" atomic" if atomic else "") + " push " + failure_push_msg + " with git. Make sure user 'pnc-user' has push permissions to this repository",
                stderr=None,
                cwd=dir
            )

        ver = yield from version()
        doAtomic = tryAtomic if versionGreaterEqualsThan(ver, [2, 4]) else False
        if tryAtomic and not doAtomic:
            logger.warn("Cannot perform atomic push. It is not supported in this git version " + '.'.join(
                [str(e) for e in ver]))

        try:
            yield from do(doAtomic)
        except exception.CommandError as e:
            if "support" in e.stderr:
                logger.warn("The repository provider does not support atomic push. "
                            "There is a risk of tag/branch inconsistency.")
                yield from do(False)
            elif "Updates were rejected because the tag already exists in the remote" in e.stderr:
                logger.info("git push failed because tag already exists. There is no need to worry")
            else:
                raise

    @asyncio.coroutine
    def init(dir):
        yield from expect_ok(
            cmd=["git", "init"],
            cwd=dir,
            desc="Could not re-init with git",
        )

    @asyncio.coroutine
    def set_user_name(dir, name):
        yield from expect_ok(
            cmd=["git", "config", "--local", "user.name", name],
            desc="Could not set committer name with git",
            cwd=dir
        )

    @asyncio.coroutine
    def set_user_email(dir, email):
        yield from expect_ok(
            cmd=["git", "config", "--local", "user.email", email],
            desc="Could not set committer email with git",
            cwd=dir
        )

    @asyncio.coroutine
    def commit(dir, commit_message, commit_date):
        yield from expect_ok(
            cmd=["git", "commit", "-m", commit_message],
            desc="Could not commit files with git",
            env={
                "GIT_AUTHOR_DATE": commit_date,
                "GIT_COMMITTER_DATE": commit_date,
            },
            cwd=dir
        )

    @asyncio.coroutine
    def rev_parse(dir, rev="HEAD"):
        res = yield from expect_ok(
            cmd=["git", "rev-parse", rev],
            desc="Could not get " + rev + " commitid with git",
            stdout="single",
            cwd=dir
        )
        return res

    @asyncio.coroutine
    def create_branch_checkout(dir, branch_name, orphan=False):
        yield from expect_ok(
            cmd=["git", "checkout", "--orphan" if orphan else "-b", branch_name],
            desc="Could not create branch with git",
            cwd=dir
        )

    @asyncio.coroutine
    def add_all(dir):
        yield from expect_ok(
            cmd=["git", "add", "-A"],
            desc="Could not add files with git",
            cwd=dir
        )

    @asyncio.coroutine
    def delete_branch(dir, branch_name):
        yield from expect_ok(
            cmd=["git", "branch", "-d", branch_name],
            desc="Could not delete temporary branch with git",
            cwd=dir
        )

    @asyncio.coroutine
    def tag_annotated(dir, tag_name, message, ok_if_exists=False):
        try:
            yield from expect_ok(
                cmd=["git", "tag", "-a", "-m", message, tag_name],
                desc="Could not add tag with git",
                cwd=dir
            )
        except exception.CommandError as e:
            if ("already exists" in e.stderr) and ok_if_exists:
                pass # ok
            else:
                raise e


    @asyncio.coroutine
    def clone_checkout_ref_auto(dir, url, ref):
        """
        Clone and checkout ref as shallowly as possible
        """
        try:
            yield from clone_checkout_branch_tag_shallow(dir, url, ref)
        except exception.CommandError as e:
            if "does not support" in e.stderr:
                # Fallback to single branch (for dumb http transport)
                try:
                    yield from clone_checkout_branch_tag_deep(dir, url, ref)
                except exception.CommandError as e:
                    # Fallback to deep+checkout (for commitid)
                    if "not found" in e.stderr:
                        yield from clone_deep(dir, url)
                        yield from checkout(dir, ref)
                    else:
                        raise
            elif "not found" in e.stderr:
                # Fallback to deep+checkout (for commitid)
                yield from clone_deep(dir, url)
                yield from checkout(dir, ref)
            else:
                raise

    @asyncio.coroutine
    def cleanup(dir):
        yield from asutil.rmtree(os.path.join(dir, ".git"))

    @asyncio.coroutine
    def version():  # TODO cache?
        """
        Return an array with components of the current git version (as numbers, ordered from most significant)
        """
        out = yield from expect_ok(
            cmd=["git", "--version"],
            desc="Could not find out git version.",
            stdout=asutil.process_stdout_options["text"]
        )
        regex = r"git\ version\ (?P<res>([0-9]+\.)*[0-9]+)"
        match = re.search(regex, out)
        if (match):
            return [int(e) for e in match.group("res").split(".")]
        else:
            raise Exception("Unexpected output of 'git --version': " + str(out))

    def versionGreaterEqualsThan(first, second):
        """
        Versions MUST be non-empty arrays of numbers ordered from most significant part.
        """
        lower = min(len(first), len(second))
        higher = max(len(first), len(second))
        if lower == 0:
            raise Exception("Versions must not be empty.")
        for i in range(0, higher):
            f = first[i] if i < len(first) else 0
            s = second[i] if i < len(second) else 0
            if f > s:
                return True
            if f < s:
                return False
        return True  # equals

    # TODO make this a class
    return {
        "version": version,
        "init": init,
        "add_remote": add_remote,
        "add_branch": add_branch,
        "delete_branch": delete_branch,
        "push_force": push_force,
        "push_with_tags": push_with_tags,
        "is_branch": is_branch,
        "clone": clone,
        "clone_deep": clone_deep,
        "checkout": checkout,
        "clone_checkout_branch_tag_shallow": clone_checkout_branch_tag_shallow,
        "clone_checkout_branch_tag_deep": clone_checkout_branch_tag_deep,
        "clone_checkout_ref_auto": clone_checkout_ref_auto,
        "cleanup": cleanup,
        "set_user_name": set_user_name,
        "set_user_email": set_user_email,
        "commit": commit,
        "rev_parse": rev_parse,
        "create_branch_checkout": create_branch_checkout,
        "add_all": add_all,
        "tag_annotated": tag_annotated
    }
