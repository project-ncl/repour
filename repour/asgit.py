import asyncio
import logging

from . import exception

logger = logging.getLogger(__name__)

#
# Common operations
#

@asyncio.coroutine
def setup_commiter(expect_ok, repo_dir):
    yield from expect_ok(
        cmd=["git", "-C", repo_dir, "config", "--local", "user.name", "Repour"],
        desc="Could not set committer name with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", repo_dir, "config", "--local", "user.email", "<>"],
        desc="Could not set committer email with git",
    )

@asyncio.coroutine
def fixed_date_commit(expect_ok, repo_dir, commit_message, commit_date="1970-01-01 00:00:00 +0000"):
    # To maintain an identical commitid for identical trees, use a fixed author/commit date.
    yield from expect_ok(
        cmd=["git", "-C", repo_dir, "commit", "-m", commit_message],
        desc="Could not commit files with git",
        env={
            "GIT_AUTHOR_DATE": commit_date,
            "GIT_COMMITTER_DATE": commit_date,
        },
    )
    head_commitid = yield from expect_ok(
        cmd=["git", "-C", repo_dir, "rev-parse", "HEAD"],
        desc="Could not get HEAD commitid with git",
        stdout="single",
    )
    return head_commitid

@asyncio.coroutine
def prepare_new_branch(expect_ok, repo_dir, branch_name, orphan=False):
    yield from expect_ok(
        cmd=["git", "-C", repo_dir, "checkout", "--orphan" if orphan else "-b", branch_name],
        desc="Could not create branch with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", repo_dir, "add", "-A"],
        desc="Could not add files with git",
    )

@asyncio.coroutine
def replace_branch(expect_ok, repo_dir, current_branch_name, new_name):
    yield from expect_ok(
        cmd=["git", "-C", repo_dir, "checkout", "-b", new_name],
        desc="Could not create replacement branch with git",
    )
    yield from expect_ok(
        cmd=["git", "-C", repo_dir, "branch", "-d", current_branch_name],
        desc="Could not delete temporary branch with git",
    )

@asyncio.coroutine
def annotated_tag(expect_ok, repo_dir, tag_name, message):
    yield from expect_ok(
        cmd=["git", "-C", repo_dir, "tag", "-a", "-m", message, tag_name],
        desc="Could not add tag with git",
    )

@asyncio.coroutine
def push_with_tags(expect_ok, repo_dir, branch_name):
    yield from expect_ok(
        cmd=["git", "-C", repo_dir, "push", "--atomic", "--follow-tags", "origin", branch_name],
        desc="Could not push tag+branch with git",
    )

#
# Higher-level operations
#

@asyncio.coroutine
def push_new_dedup_branch(expect_ok, repo_dir, repo_url, operation_name, operation_description, orphan=False, no_change_ok=False):
    # There are a few priorities for reference names:
    #   - Amount of information in the name itself
    #   - Length
    #   - Parsability
    # The following scheme does not include the origin_ref, although it is good
    # information, because it comprimises length and parsability too much.

    # As many things as possible are controlled for the commit, so the commitid
    # can be used for deduplication.
    temp_branch = "repour_commitid_search_temp_branch"
    yield from prepare_new_branch(expect_ok, repo_dir, temp_branch, orphan=orphan)

    try:
        commit_id = yield from fixed_date_commit(expect_ok, repo_dir, "Repour")
    except exception.CommandError as e:
        if no_change_ok and e.exit_code == 1:
            # No changes were made
            return None
        else:
            raise

    # Apply the actual branch name now we know the commit ID
    operation_name_lower = operation_name.lower()
    branch_name = "branch-{operation_name_lower}-{commit_id}".format(**locals())
    yield from replace_branch(expect_ok, repo_dir, temp_branch, branch_name)

    tag_name = "repour-{commit_id}".format(**locals())
    yield from annotated_tag(expect_ok, repo_dir, tag_name, operation_description)
    # The tag and reference names are set up to be the same for the same
    # file tree, so this is a deduplicated operation. If the branch/tag
    # already exist, git will return quickly with an 0 (success) status
    # instead of uploading the objects.
    yield from push_with_tags(expect_ok, repo_dir, branch_name)

    logger.info("Pushed branch {branch_name} to repo {repo_url}".format(**locals()))

    return {
        "branch": branch_name,
        "tag": tag_name,
        "url": {
            "readwrite": repo_url.readwrite,
            "readonly": repo_url.readonly,
        },
    }
