import asyncio
import logging

from . import exception
from .config import config
from .scm import git_provider

logger = logging.getLogger(__name__)

#
# Common operations
#

c = config.get_configuration_sync()
git = git_provider.git_provider()


@asyncio.coroutine
def setup_commiter(expect_ok, repo_dir):
    yield from git["set_user_name"](repo_dir, c.get("scm", {}).get("git", {}).get("user.name", "Repour"))
    yield from git["set_user_email"](repo_dir, c.get("scm", {}).get("git", {}).get("user.email", "<>"))


@asyncio.coroutine
def fixed_date_commit(expect_ok, repo_dir, commit_message, commit_date="1970-01-01 00:00:00 +0000"):
    # To maintain an identical commitid for identical trees, use a fixed author/commit date.
    yield from git["commit"](repo_dir, commit_message, commit_date)
    head_commitid = yield from git["rev_parse"](repo_dir)
    return head_commitid


@asyncio.coroutine
def prepare_new_branch(expect_ok, repo_dir, branch_name, orphan=False):
    yield from git["create_branch_checkout"](repo_dir, branch_name, orphan)
    yield from git["add_all"](repo_dir)


@asyncio.coroutine
def replace_branch(expect_ok, repo_dir, current_branch_name, new_name):
    yield from git["create_branch_checkout"](repo_dir, new_name)
    yield from git["delete_branch"](repo_dir, current_branch_name)


@asyncio.coroutine
def annotated_tag(expect_ok, repo_dir, tag_name, message, ok_if_exists=False):
    yield from git["tag_annotated"](repo_dir, tag_name, message, ok_if_exists)


@asyncio.coroutine
def push_with_tags(expect_ok, repo_dir, branch_name):
    yield from git["push_with_tags"](repo_dir, branch_name, tryAtomic=True)


#
# Higher-level operations
# Returns None if no changes were made and no_change_ok=True, else raises an exception
# If no_change_ok=True you may set force_continue_on_no_changes to create the branch and tag anyway,
# on the current ref, without making the new commit
#

@asyncio.coroutine
def push_new_dedup_branch(expect_ok, repo_dir, repo_url, operation_name, operation_description, orphan=False,
                          no_change_ok=False, force_continue_on_no_changes=False):
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
            if force_continue_on_no_changes:
                # Use the current commit to continue
                commit_id = yield from git["rev_parse"](repo_dir)
            else:
                return None
        else:
            raise

    # Apply the actual branch name now we know the commit ID
    operation_name_lower = operation_name.lower()
    branch_name = "branch-{operation_name_lower}-{commit_id}".format(**locals())
    yield from replace_branch(expect_ok, repo_dir, temp_branch, branch_name)

    tag_name = "repour-{commit_id}".format(**locals())

    try:
        yield from annotated_tag(expect_ok, repo_dir, tag_name, operation_description, ok_if_exists=force_continue_on_no_changes)
    except exception.CommandError as e:
        if no_change_ok and e.exit_code == 1:
            # No changes were made
            if force_continue_on_no_changes:
                return None
        else:
            raise

    # The tag and reference names are set up to be the same for the same
    # file tree, so this is a deduplicated operation. If the branch/tag
    # already exist, git will return quickly with an 0 (success) status
    # instead of uploading the objects.
    yield from push_with_tags(expect_ok, repo_dir, branch_name)

    logger.info("Pushed to repo: branch {branch_name}, tag {tag_name}".format(**locals()))

    return {
        "branch": branch_name,
        "tag": tag_name,
        "url": {
            "readwrite": repo_url.readwrite,
            "readonly": repo_url.readonly,
        },
    }
