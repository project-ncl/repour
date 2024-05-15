# Git utility functions
#
# Use this module for all operations involving git
#
# Note that all functions are async

import logging
import os
import random
import re
import string
import subprocess

from repour import asutil, exception

logger = logging.getLogger(__name__)

expect_ok = asutil.expect_ok_closure(exception.CommandError)


async def disable_bare_repository(dir):
    await expect_ok(
        cmd=["git", "config", "--bool", "core.bare", "false"],
        cwd=dir,
        desc="Could not disable bare repository",
        print_cmd=True,
    )


async def reset_hard(dir):
    await expect_ok(
        cmd=["git", "reset", "--hard"],
        cwd=dir,
        desc="Could not reset hard",
        print_cmd=True,
    )


async def clone_deep(dir, url):
    desc = "Could not clone {} with git.".format(url)

    if "github.com" in url:
        desc += " " + private_github_error_msg(url)

    await expect_ok(cmd=["git", "clone", "--", url, dir], desc=desc, print_cmd=True)


async def checkout(dir, ref, force=False):
    # Checkout tag or branch or commit-id
    cmd = ["git", "checkout"]

    if force:
        cmd.append("-f")

    cmd.append(ref)
    # See NCL-5173 why we need to add '--' at the end
    cmd.append("--")

    try:
        await expect_ok(
            cmd=cmd,
            cwd=dir,
            desc="Could not checkout ref {ref} with git".format(**locals()),
            print_cmd=True,
        )
    except exception.CommandError as e:
        e.exit_code = 10
        raise


async def checkout_pr(dir, ref, remote="origin"):
    """
    Checkout a PR ref to a branch. The name of the branch is returned

    The PR ref has to be in a format as specified in 'is_ref_a_pull_request'

    Parameters:
    - dir: :string: directory of git repo
    - ref: :string: ref of the PR
    - remote: :string: the remote to use (default: origin)

    return:
    - branch where PR is checkout :string:
    """
    if not is_ref_a_pull_request(ref):
        error_desc = "Reference {} is not a PR!".format(ref)
        raise exception.AdjustCommandError(
            str(error_desc), [], 10, stderr=str(error_desc)
        )

    modified_fetch_ref, branch = modify_ref_to_be_fetchable(ref)
    try:
        await expect_ok(
            cmd=["git", "fetch", remote, modified_fetch_ref],
            cwd=dir,
            desc="fetch pr to a branch",
            print_cmd=True,
        )
        await checkout(dir, branch)
        return branch

    except exception.CommandError as e:
        e.exit_code = 10
        raise


async def clone_checkout_branch_tag_shallow(dir, url, branch_or_tag):
    desc = "Could not clone {} with git.".format(url)

    if "github.com" in url:
        desc += " " + private_github_error_msg(url)

    await expect_ok(
        cmd=[
            "git",
            "clone",
            "--branch",
            branch_or_tag,
            "--depth",
            "1",
            "--",
            url,
            dir,
        ],
        desc=desc,
        stderr=None,
        print_cmd=True,
    )


async def clone_checkout_branch_tag_deep(dir, url, branch_or_tag):
    desc = "Could not clone {} with git.".format(url)

    if "github.com" in url:
        desc += " " + private_github_error_msg(url)

    await expect_ok(
        cmd=["git", "clone", "--branch", branch_or_tag, "--", url, dir],
        desc=desc,
        stderr=None,
        print_cmd=True,
    )


async def clone(dir, url):
    desc = "Could not clone {} with git.".format(url)

    if "github.com" in url:
        desc += " " + private_github_error_msg(url)

    try:
        await expect_ok(cmd=["git", "clone", "--", url, dir], desc=desc, print_cmd=True)
    except exception.CommandError as e:
        e.exit_code = 10
        raise


async def clone_mirror(dir, url):
    desc = "Could not clone mirror {} with git.".format(url)

    if "github.com" in url:
        desc += " " + private_github_error_msg(url)

    await expect_ok(
        cmd=["git", "clone", "--mirror", "--", url, dir], desc=desc, print_cmd=True
    )


async def add_tag(dir, name):
    await expect_ok(
        cmd=["git", "tag", name],
        cwd=dir,
        desc="Could not add tag {} with git.".format(name),
        print_cmd=True,
    )


async def remove_remote(dir, name):
    await expect_ok(
        cmd=["git", "remote", "remove", name],
        cwd=dir,
        desc="Could not remove remote {} with git.".format(name),
        print_cmd=True,
    )


async def rename_remote(dir, old_name, new_name):
    await expect_ok(
        cmd=["git", "remote", "rename", old_name, new_name],
        cwd=dir,
        desc="Could not remove rename remote '{}' to '{}'".format(old_name, new_name),
        print_cmd=True,
    )


async def add_remote(dir, name, url):
    await expect_ok(
        cmd=["git", "remote", "add", name, url, "--"],
        cwd=dir,
        desc="Could not add remote {} with git.".format(url),
        print_cmd=True,
    )


async def rm(dir, path_in_repository, cached=False):
    """
    git rm a path in git

    Parameters:
    - dir: git repository location
    - path_in_repository is relative to the repository.
    - cached: remove from cache or not
    """

    command = ["git", "rm"]

    if cached:
        command.append("--cached")

    command.append(path_in_repository)

    await expect_ok(
        cmd=command,
        cwd=dir,
        desc="Could not remove {} with git.".format(dir),
        print_cmd=True,
    )


async def does_sha_exist(dir, ref):
    try:
        # do not log stderr to output on failure. this causes useless error logs to be printed if ref is not a branch
        await expect_ok(
            cmd=["git", "cat-file", "-e", ref + "^{commit}"],
            cwd=dir,
            desc="Ignore this.",
            print_cmd=True,
            stderr=None,
        )
        return True
    except Exception:
        return False


async def does_pr_exist(dir, ref, remote="origin"):
    if not is_ref_a_pull_request(ref):
        return False

    try:
        await expect_ok(
            cmd=[
                "git",
                "fetch",
                remote,
                modify_ref_to_be_fetchable(ref)[0],
                "--dry-run",
            ],
            cwd=dir,
            desc="Ignore this.",
            print_cmd=True,
        )
        return True
    except Exception:
        return False


async def is_branch(dir, ref, remote="origin"):
    # Need to run this for show-branch to work effectively
    await fetch(dir)

    # do not log stderr to output on failure. this causes useless error logs to be printed if ref is not a branch
    try:  # TODO improve, its ugly
        await expect_ok(
            cmd=["git", "show-branch", "remotes/" + remote + "/" + ref],
            cwd=dir,
            desc="Ignore this.",
            print_cmd=True,
            stderr=None,
        )
        return True
    except Exception:
        return False


async def is_tag(dir, ref):
    try:  # TODO improve, its ugly
        await expect_ok(
            cmd=["git", "show-ref", "--quiet", "--tags", ref, "--"],
            cwd=dir,
            desc="Ignore this.",
            print_cmd=True,
            stderr=None,
        )
        return True
    except Exception:
        return False


async def add_branch(dir, name):
    await expect_ok(
        cmd=["git", "branch", name, "--"],
        cwd=dir,
        desc="Could not add branch {} with git.".format(name),
        print_cmd=True,
    )


async def push_force(dir, remote, branch_or_tag):  # Warning! --force
    await push(dir, remote, branch_or_tag, force=True)


async def push(dir, remote, branch_or_tag, force=False):
    cmd = ["git", "push"]

    if force:
        cmd.append("--force")

    cmd.extend([remote, branch_or_tag, "--"])

    try:
        await expect_ok(
            cmd=cmd,
            cwd=dir,
            desc="Could not push branch or tag '{}' to remote '{}' with git".format(
                branch_or_tag, remote
            ),
            print_cmd=True,
        )
    except exception.CommandError as e:
        e.exit_code = 10
        raise


async def push_all(dir, remote, tags_also=False):
    cmd = ["git", "push", "--all"]

    cmd.extend([remote, "--"])

    await expect_ok(
        cmd=cmd,
        cwd=dir,
        desc="Could not push all to remote '{}' with git".format(remote),
        print_cmd=True,
    )

    if tags_also:
        cmd_tag = ["git", "push", "--tags", remote, "--"]
        await expect_ok(
            cmd=cmd_tag,
            cwd=dir,
            desc="Could not push all tags to remote '{}' with git".format(remote),
            print_cmd=True,
        )


# TODO merge with above
async def push_with_tags(
    dir,
    branch,
    config_git_user,
    remote="origin",
    tryAtomic=False,
    ignore_tag_already_exist_error=False,
):
    """
    Warning: Atomic push is supported since git version 2.4.
    If the atomic push is not supported by git client OR repository provider,
    this method re-tries without it and returns false.
    If an exception is thrown, some other error occurred and push did not
    succeed.

    If branch is None, it is assumed that you only want to push the tags
    """

    async def do(atomic):
        if branch is None:
            options = ["--tags"]
            failure_push_msg = "tag"
        else:
            tags = await list_reachable_tags_from_ref(dir, branch)
            options = [remote, branch]
            if not tags:
                options += ["tag"] + tags
            failure_push_msg = "tag+branch"

        process = subprocess.Popen(
            ["git", "config", "remote.%s.url" % remote], stdout=subprocess.PIPE
        )
        url_value = process.communicate()[0].decode("utf-8").strip()

        scmurl_regex = re.compile("^.*://([^@]+)@.*$")
        scmurl = scmurl_regex.search(url_value)
        if scmurl:
            git_user = scmurl.group(1)
        else:
            git_user = config_git_user

        await expect_ok(
            cmd=["git", "push"] + (["--atomic"] if atomic else []) + options,
            desc="Could not"
            + (" atomic" if atomic else "")
            + " push "
            + failure_push_msg
            + " with git. Make sure user '"
            + git_user
            + "' has push permissions to this repository",
            cwd=dir,
            print_cmd=True,
        )

    ver = await version()
    doAtomic = tryAtomic if versionGreaterEqualsThan(ver, [2, 4]) else False
    if tryAtomic and not doAtomic:
        logger.warn(
            "Cannot perform atomic push. It is not supported in this git version "
            + ".".join([str(e) for e in ver])
        )

    try:
        await do(doAtomic)
    except exception.CommandError as e:
        if "support" in e.stderr:
            logger.warn(
                "The repository provider does not support atomic push. "
                "There is a risk of tag/branch inconsistency."
            )
            await do(False)
        elif ignore_tag_already_exist_error and (
            "Updates were rejected because the tag already exists in the remote"
            in e.stderr
        ):
            logger.info(
                "git push failed because tag already exists. There is no need to worry"
            )
        else:
            e.exit_code = 10
            raise


async def init(dir):
    await expect_ok(cmd=["git", "init"], cwd=dir, desc="Could not re-init with git")


async def set_user_name(dir, name):
    await expect_ok(
        cmd=["git", "config", "--local", "user.name", name],
        desc="Could not set committer name with git",
        cwd=dir,
        print_cmd=True,
    )


async def set_user_email(dir, email):
    await expect_ok(
        cmd=["git", "config", "--local", "user.email", email],
        desc="Could not set committer email with git",
        cwd=dir,
        print_cmd=True,
    )


async def commit(dir, commit_message, commit_date=None):
    if commit_date:
        env = {"GIT_AUTHOR_DATE": commit_date, "GIT_COMMITTER_DATE": commit_date}
    else:
        env = {}

    await expect_ok(
        cmd=["git", "commit", "-m", commit_message],
        desc="Could not commit files with git",
        env=env,
        cwd=dir,
        print_cmd=True,
    )


async def rev_parse(dir, rev="HEAD"):
    res = await expect_ok(
        cmd=["git", "rev-parse", rev],
        desc="Could not get " + rev + " commitid with git",
        stdout="single",
        cwd=dir,
    )
    return res


async def current_branch(dir):
    res = await expect_ok(
        cmd=["cat", ".git/HEAD"],
        desc="Could not get branch with git",
        stdout="single",
        cwd=dir,
    )
    return res


async def create_branch_checkout(dir, branch_name, orphan=False):
    output = await expect_ok(
        cmd=["git", "checkout", "--orphan" if orphan else "-b", branch_name],
        desc="Could not create branch with git",
        stdout="text",
        cwd=dir,
        print_cmd=True,
    )
    logger.info(str(output))


async def create_branch_from_commit(dir, branch_name, commit):
    output = await expect_ok(
        cmd=["git", "checkout", "-b", branch_name, commit],
        desc="Could not create branch with git",
        stdout="text",
        cwd=dir,
        print_cmd=True,
    )
    logger.info(str(output))


async def add_all(dir):
    await expect_ok(
        cmd=["git", "add", "-A"],
        desc="Could not add files with git",
        cwd=dir,
        print_cmd=True,
    )


async def add_file(dir, file_path, force=False):
    """
    file_path  is relative to the dir
    Add individual file to Git. force option provided to ignore .gitignore if needed
    """
    command = ["git", "add"]
    if force:
        command.append("-f")
    command.append(file_path)

    await expect_ok(
        cmd=command, desc="Could not add file with git", cwd=dir, print_cmd=True
    )


async def fetch_tags(dir, remote="origin"):
    try:
        await expect_ok(
            cmd=["git", "fetch", remote, "--tags"],
            desc="Could not fetch tags with git",
            cwd=dir,
            print_cmd=True,
            stderr="log_on_error_as_info",
        )
    except exception.CommandError as e:
        e.exit_code = 10
        raise


async def fetch(dir):
    try:
        await expect_ok(
            cmd=["git", "fetch"],
            desc="Could not fetch tags with git",
            cwd=dir,
            print_cmd=True,
        )
    except exception.CommandError as e:
        e.exit_code = 10
        raise


async def delete_branch(dir, branch_name):
    await expect_ok(
        cmd=["git", "branch", "-d", branch_name],
        desc="Could not delete temporary branch with git",
        cwd=dir,
        print_cmd=True,
    )


async def tag_annotated(dir, tag_name, message, ok_if_exists=False):
    try:
        await expect_ok(
            cmd=["git", "tag", "-a", "-m", message, tag_name],
            desc="Could not add tag with git",
            cwd=dir,
            print_cmd=True,
        )
    except exception.CommandError as e:
        if ("already exists" in e.stderr) and ok_if_exists:
            pass  # ok
        else:
            raise e


async def write_tree(dir):
    """
    Get the tree SHA from current index
    """
    tree_sha = await expect_ok(
        cmd=["git", "write-tree"],
        desc="Couldn't get the commit tree with git",
        stdout="text",
        cwd=dir,
        print_cmd=True,
    )
    return tree_sha.strip()


async def get_tag_from_tree_sha(dir, tree_sha):
    """
    Return the tag for a particular tree SHA
    Return None if no such tag exists
    """

    def get_tag_name(temp_tags):
        """
        temp_tags is in format: '(tag: <tag1>, <tag2>, <tag3> ...)'
        return first tag (aka tag1)

        We use '%d' to get the refname since there are no support for %D in
        git 1.8.3, the version we use in RHEL 7
        """
        if "tag:" in temp_tags:
            temp_tags = temp_tags.strip()
            # Remove beginning and ending '(' ')'
            if temp_tags.startswith("("):
                temp_tags = temp_tags[1:]
            if temp_tags.endswith(")"):
                temp_tags = temp_tags[:-1]

            comma_delimited_tags = re.sub(r"^.*tag:", "", temp_tags.strip()).strip()
            return comma_delimited_tags.split(",")[0]
        else:
            return None

    try:
        data = await expect_ok(
            # separate the tree SHA and the tag information with '::'
            # output is <tree_sha>:: (tag: <tag1>, <tag2>, ...)
            cmd=[
                "git",
                "--no-pager",
                "log",
                "--tags",
                "--no-walk",
                '--pretty="%T::%d"',
            ],
            desc="Couldn't get the tree hash / tag relationship via git log",
            stdout="lines",
            cwd=dir,
            print_cmd=True,
        )
        # Each line contains information about a tree sha, and the tag(s) pointing to it indirectly
        for item in data:
            # For some reason the text from 'expect_ok' are in quotes. Remove it
            item = item.replace('"', "")

            temp_tree_sha, temp_tags = item.split("::")

            if temp_tree_sha.strip() == tree_sha.strip():
                return get_tag_name(temp_tags)
        else:
            return None

    except exception.CommandError as e:
        # No commits yet in the tag
        if "does not have any commits yet" in e.stderr:
            return None


async def get_commit_from_tag_name(repo_dir, tag_name):
    commit = await expect_ok(
        cmd=["git", "rev-list", "-n", "1", tag_name],
        desc="Couldn't get the commit from tag with git",
        stdout="text",
        cwd=repo_dir,
        print_cmd=True,
    )

    return commit.strip()


async def clone_checkout_ref_auto(dir, url, ref):
    """
    Clone and checkout ref as shallowly as possible
    """
    try:
        await clone_checkout_branch_tag_shallow(dir, url, ref)
    except exception.CommandError as e:
        if "does not support" in e.stderr:
            # Fallback to single branch (for dumb http transport)
            try:
                await clone_checkout_branch_tag_deep(dir, url, ref)
            except exception.CommandError as e:
                # Fallback to deep+checkout (for commitid)
                if "not found" in e.stderr:
                    await clone_deep(dir, url)
                    await checkout(dir, ref)
                else:
                    raise
        elif "not found" in e.stderr:
            # Fallback to deep+checkout (for commitid)
            await clone_deep(dir, url)
            await checkout(dir, ref)
        else:
            raise


async def cleanup(dir):
    await asutil.rmtree(os.path.join(dir, ".git"))


async def show_current_commit(repo_dir):
    commit = await expect_ok(
        cmd=["git", "rev-parse", "HEAD"],
        desc="Couldn't get the commit from the repository",
        stdout="text",
        cwd=repo_dir,
        print_cmd=True,
    )

    return commit.strip()


async def version():  # TODO cache?
    """
    Return an array with components of the current git version (as numbers, ordered from most significant)
    """
    out = await expect_ok(
        cmd=["git", "--version"],
        desc="Could not find out git version.",
        stdout=asutil.process_stdout_options["text"],
    )
    regex = r"git\ version\ (?P<res>([0-9]+\.)*[0-9]+)"
    match = re.search(regex, out)
    if match:
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


def private_github_error_msg(url):
    """
    If a user is trying to clone a private Github repository, we should tell the user what to do to get the clone working.
    It's expecting the environment variable 'PRIVATE_GITHUB_USER' to be set.

    returns: string with proper message to tell the user what to do
    """
    try:
        github_user = os.environ["PRIVATE_GITHUB_USER"]
    except KeyError:
        # if environment variable not specified
        logger.warn("PRIVATE_GITHUB_USER environment variable not specified!")
        github_user = None

    if github_user:
        further_desc = (
            "If the Github repository is a private repository, you need to add the Github user "
            + "'{user}' with read-permissions to '{url}'".format(
                user=github_user, url=url
            )
        )
    else:
        further_desc = (
            "If the Github repository is a private repository, you need to add a Github user "
            + "with read-permissions to '{url}'. Please email the Newcastle mailing list for more information".format(
                url=url
            )
        )

    return further_desc


async def list_tags(dir):
    """
    Returns list of tags
    """
    tags = await expect_ok(
        cmd=["git", "tag"],
        desc="Couldn't get the list of tags",
        stdout="text",
        cwd=dir,
        print_cmd=True,
    )
    return list(filter(None, [a.strip() for a in tags.split("\n")]))


async def list_reachable_tags_from_ref(dir, ref="HEAD"):
    """
    Returns list of tags reachable from a ref
    """
    tags = await expect_ok(
        cmd=["git", "tag", "--merged", ref],
        desc="Couldn't get the list of tags",
        stdout="text",
        cwd=dir,
        print_cmd=True,
    )
    return list(filter(None, [a.strip() for a in tags.split("\n")]))


async def list_branches(dir):
    """
    Returns list of branches
    """
    branches = await expect_ok(
        cmd=["git", "branch", "-a"],
        desc="Couldn't get the list of branches",
        stdout="text",
        cwd=dir,
        print_cmd=True,
    )
    return list(filter(None, [a.strip() for a in branches.split("\n")]))


async def submodule_update_init(dir):
    """
    Run 'git submodule update --init' to initialize the git submodules
    """
    await expect_ok(
        cmd=["git", "submodule", "update", "--init"],
        cwd=dir,
        desc="Could not initiate submodules with git in path {}.".format(dir),
        print_cmd=True,
    )


def is_ref_a_pull_request(ref):
    """
    Check if the ref is a pull request

    Supported ref format:
    - merge-requests/<number> for Gitlab
    - pull/<number> for Github

    Parameters:
    - ref: :string:

    Return:
    - :bool:
    """
    gitlab_check = re.compile(r"merge-requests/\d+")
    github_check = re.compile(r"pull/\d+")

    if gitlab_check.search(ref):
        return True

    if github_check.search(ref):
        return True

    # No match found
    return False


def modify_ref_to_be_fetchable(ref):
    """
    Return a tuple (ref to fetch to branch, branch) for a ref which is a pull request.

    For example, if the ref is: merge-requests/10, then the returned value is:
        ('merge-requests/10/head:random_branch_name', 'random_branch_name')

    The string of the first element of the tuple can then be used in 'git fetch' to pull the pull request locally into branch: random_branch_name

    If the ref is not a pull request, a tupe of (None, None) is returned

    Parameters:
    - ref: :string: ref of a merge request

    Return:
    - tuple: first element is a ref that can be 'git fetched', the second is the random branch where the ref is checkout
    """

    if is_ref_a_pull_request(ref):
        random_branch_name = "".join(
            random.choice(string.ascii_letters) for i in range(10)
        )
        return (ref + "/head:" + random_branch_name, random_branch_name)
    else:
        return (None, None)
