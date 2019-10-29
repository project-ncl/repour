import logging
import uuid

from . import exception
from .config import config
from .scm import git_provider

logger = logging.getLogger(__name__)

#
# Common operations
#

c = config.get_configuration_sync()
git = git_provider.git_provider()


async def setup_commiter(expect_ok, repo_dir):
    await git["set_user_name"](
        repo_dir, c.get("scm", {}).get("git", {}).get("user.name", "Repour")
    )
    await git["set_user_email"](
        repo_dir, c.get("scm", {}).get("git", {}).get("user.email", "<>")
    )


async def fixed_date_commit(
    expect_ok, repo_dir, commit_message, commit_date="1970-01-01 00:00:00 +0000"
):
    # To maintain an identical commitid for identical trees, use a fixed author/commit date.
    await git["commit"](repo_dir, commit_message, commit_date)
    head_commitid = await git["rev_parse"](repo_dir)
    return head_commitid


async def normal_date_commit(expect_ok, repo_dir, commit_message):
    commit_id = await fixed_date_commit(
        expect_ok, repo_dir, commit_message, commit_date=None
    )
    return commit_id


async def prepare_new_branch(expect_ok, repo_dir, branch_name, orphan=False):
    await git["create_branch_checkout"](repo_dir, branch_name, orphan)
    await git["add_all"](repo_dir)


async def replace_branch(expect_ok, repo_dir, current_branch_name, new_name):
    await git["create_branch_checkout"](repo_dir, new_name)
    await git["delete_branch"](repo_dir, current_branch_name)


async def annotated_tag(expect_ok, repo_dir, tag_name, message, ok_if_exists=False):
    await git["tag_annotated"](repo_dir, tag_name, message, ok_if_exists=ok_if_exists)


async def push_with_tags(expect_ok, repo_dir, branch_name):
    c = await config.get_configuration()
    git_user = c.get("git_username")

    await git["push_with_tags"](repo_dir, branch_name, git_user, tryAtomic=True)


#
# Higher-level operations
# Returns tag information
# If no_change_ok=True you may set force_continue_on_no_changes to create the branch and tag anyway,
# on the current ref, without making the new commit
#


async def push_new_dedup_branch(
    expect_ok,
    repo_dir,
    repo_url,
    operation_name,
    operation_description,
    orphan=False,
    no_change_ok=False,
    force_continue_on_no_changes=False,
    real_commit_time=False,
    specific_tag_name=None,
):
    # There are a few priorities for reference names:
    #   - Amount of information in the name itself
    #   - Length
    #   - Parsability
    # The following scheme does not include the origin_ref, although it is good
    # information, because it comprimises length and parsability too much.
    tag_name = None
    commit = None

    # As many things as possible are controlled for the commit, so the commitid
    # can be used for deduplication.
    temp_branch = "repour_commitid_search_temp_branch_" + str(uuid.uuid1())
    await prepare_new_branch(expect_ok, repo_dir, temp_branch, orphan=orphan)

    if real_commit_time:
        # prepare_new_branch does a git add all, so calling git write-tree
        # should give the current tree SHA of the directory
        tree_sha = await git["write_tree"](repo_dir)

        # Find if there's already a tag for the tree sha above
        tag_name = await git["get_tag_from_tree_sha"](repo_dir, tree_sha)

        if tag_name:
            commit = await git["get_commit_from_tag_name"](repo_dir, tag_name)

        # Find if tree sha already exists in a tag
        # - yes -> return existing tag, if no_change_ok = true
        #       -> raise exception if no_change_ok = false
        # - no  -> create new commit with regular date, create tag and push
        if tag_name and not no_change_ok:
            raise

    # we are here either if we are not using real_commit_time or if we couldn't
    # find the tag using the tree SHA
    if tag_name is None:
        logger.info(
            "No existing commit/tag with changes to commit ispresent. Creating new commit/tag"
        )
        tag_name = await commit_push_tag(
            expect_ok,
            repo_dir,
            operation_name,
            operation_description,
            no_change_ok,
            force_continue_on_no_changes,
            real_commit_time,
            specific_tag_name,
        )

        commit = await git["get_commit_from_tag_name"](repo_dir, tag_name)
    else:
        logger.info("Existing tag containing changes to commit is present. Using it")
        logger.info("Tag name is: {0}".format(tag_name))
        # If tag name already exists, make sure it's already present in upstream
        # This happens if we are doing /adjust, with pre-sync enabled.
        # The external repo might have the tag, but not the internal repo
        await push_with_tags(expect_ok, repo_dir, tag_name)

    if tag_name is None:
        return None
    else:
        return {
            "tag": tag_name,
            "commit": commit,
            "url": {"readwrite": repo_url.readwrite, "readonly": repo_url.readonly},
        }


async def commit_push_tag(
    expect_ok,
    repo_dir,
    operation_name,
    operation_description,
    no_change_ok,
    force_continue_on_no_changes,
    real_commit_time,
    specific_tag_name=None,
):
    try:
        if real_commit_time:
            commit_id = await normal_date_commit(expect_ok, repo_dir, "Repour")
        else:
            commit_id = await fixed_date_commit(expect_ok, repo_dir, "Repour")

    except exception.CommandError as e:
        if no_change_ok and e.exit_code == 1:
            commit_id = await git["rev_parse"](repo_dir)
        else:
            raise

    # Apply the actual branch name now we know the commit ID
    operation_name_lower = operation_name.lower()

    if specific_tag_name:
        tag_name = specific_tag_name
    else:
        tag_name = "repour-{commit_id}".format(**locals())

    # Check if tag name already exists, if so, modify tag name to <tag>-{commitid}
    does_tag_exist = await git["is_tag"](repo_dir, tag_name)

    shorthand_commit_id = commit_id[:8]  # only show first 8 chars of commit id

    if does_tag_exist:
        logger.info(
            "Tag {0} already exists! Changing it to {0}-{1}".format(
                tag_name, shorthand_commit_id
            )
        )
        tag_name = "{0}-{1}".format(tag_name, shorthand_commit_id)
    elif c.get("mode", "prod") == "devel":
        # NCL-4120: if devel mode activated create tag with format: <tag>-<commitid> all the time
        # reason is to avoid conflict between official internal git repository and test git repository when we try to sync from official internal to test git
        logger.info(
            "Repour Devel mode activated! Changing tag to {0}-{1} to avoid conflict between internal git repositories".format(
                tag_name, shorthand_commit_id
            )
        )
        tag_name = "{0}-{1}".format(tag_name, shorthand_commit_id)

    try:
        await annotated_tag(
            expect_ok,
            repo_dir,
            tag_name,
            operation_description,
            ok_if_exists=force_continue_on_no_changes,
        )
    except exception.CommandError as e:
        if no_change_ok and e.exit_code == 1:
            # No changes were made
            if force_continue_on_no_changes:
                return None
        else:
            raise

    # The tag and reference names are set up to be the same for the same
    # file tree, so this is a deduplicated operation. If the tag
    # already exist, git will return quickly with an 0 (success) status
    # instead of uploading the objects.
    try:
        await push_with_tags(expect_ok, repo_dir, None)
    except exception.CommandError as e:
        # Modify the exit code to 10. This tells Maitai to not treat this as
        # a SYSTEM_ERROR (NCL-2871)
        e.exit_code = 10
        raise

    logger.info("Pushed to repo: tag {tag_name}".format(**locals()))
    return tag_name
