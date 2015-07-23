import asyncio
import logging

from . import asgit
from . import asutil
from . import exception

logger = logging.getLogger(__name__)

#
# Utility
#

expect_ok = asutil.expect_ok_closure(exception.AdjustCommandError)

@asyncio.coroutine
def commit_adjustments(repo_url, repo_dir):
    # These reference names could be appended to the existing reference, ex:
    #     pull-1437651783-root_adjust-1437651783-root
    # however, this could lead to very long nested names, ex:
    #     pull-1437651783-root_adjust-1437651783-root_adjust-1437651783-root
    # so a constant scheme is used instead.

    timestamp = unix_time()
    branch_name = "adjust-{timestamp}".format(**locals())
    tag_name = "{branch_name}-root".format(**locals())
    tag_refspec_pattern = "refs/tags/adjust-*".format(**locals())

    # TODO parent / adjust type info?
    tag_message = """
"""

    yield from asgit.prepare_new_branch(expect_ok, dirname, branch_name)
    # Adjustment could have made no changes
    try:
        yield from asgit.fixed_date_commit(expect_ok, dirname, "Adjust")
    except exception.AdjustCommandError as e:
        if e.exit_code == 1:
            # No changes were made
            return None
        else:
            raise

    # Check if any root tag in the internal repo matches the commitid we currently have.
    existing_tag = yield from asgit.deduplicate_head_tag(expect_ok, dirname, tag_refspec_pattern)

    if existing_tag is None:
        yield from asgit.annotated_tag(expect_ok, dirname, tag_name, tag_message)
        yield from asgit.push_with_tags(expect_ok, dirname, branch_name)

        logger.info("Pushed branch {branch_name} to internal repo {repo_url}".format(**locals()))

        return {
            "branch": branch_name,
            "tag": tag_name,
            "url": repo_url,
        }

    # Discard cloned branch and use existing branch and tag
    else:
        # ex: proj-1.0_1436360795_root -> proj-1.0_1436360795
        existing_branch = existing_tag[:-5]

        logger.info("Using existing branch {branch_name} in repo {repo_url}".format(**locals()))

        return {
            "branch": existing_branch,
            "tag": existing_tag,
            "url": repo_url,
        }

#
# Adjust operation
#

@asyncio.coroutine
def adjust(adjustspec, repo_provider, adjust_provider):
    with asutil.TemporaryDirectory(suffix="git") as d:
        repo_url = yield from repo_provider(adjustspec["name"], create=False)

        # Non-shallow, but branch-only clone of internal repo
        yield from expect_ok(
            cmd=["git", "clone", "--branch", adjustspec["ref"], "--", repo_url, d],
            desc="Could not clone with git",
        )
        yield from asgit.setup_commiter(expect_ok, dirname)

        yield from adjust_provider(d)

        result = yield from commit_adjustments(d)

    return result

#
# Adjust providers
#

def adjust_noop():
    @asyncio.coroutine
    def adjust(repo_dir):
        pass
    return adjust

@asyncio.coroutine
def adjust_subprocess(cmd):
    @asyncio.coroutine
    def adjust(repo_dir):
        filled_cmd = [repo_dir if p == "{repo_dir}" else p for p in cmd]
        yield from expect_ok(filled_cmd, "Alignment subprocess failed")
    return adjust

#
# Supported
#

provider_types = {
    "noop": adjust_noop,
    "subprocess": adjust_subprocess,
}
