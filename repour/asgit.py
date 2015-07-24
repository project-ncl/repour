import asyncio
import datetime
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
def deduplicate_head_tag(expect_ok, repo_dir, repo_url, refspec_pattern="refs/tags/*"):
    head_commitid = yield from expect_ok(
        cmd=["git", "-C", repo_dir, "rev-parse", "HEAD"],
        desc="Could not get HEAD commitid with git",
        stdout="single",
    )
    stdout_lines = yield from expect_ok(
        cmd=["git", "ls-remote", repo_url, refspec_pattern],
        desc="Could not read remote refs with git",
        stdout="lines",
    )
    for l in stdout_lines:
        commit_id, refspec = l.split("\t")
        if commit_id == head_commitid:
            # ex: refs/tags/proj-1.0_1436360795_root -> proj-1.0_1436360795_root
            existing_tag = refspec.split("/", 2)[-1]
            break
    else:
        existing_tag = None

    return existing_tag

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

def _unix_time(now=None):
    now = datetime.datetime.utcnow() if now is None else now
    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = now - epoch
    return round(delta.total_seconds())

@asyncio.coroutine
def push_new_dedup_branch(expect_ok, repo_dir, repo_url, operation_name, operation_description, orphan=False, no_change_ok=False):
    # There are a few priorities for reference names:
    #   - Amount of information in the name itself
    #   - Length
    #   - Parsability
    # The following scheme does not include the origin_ref, although it is good
    # information, because it comprimises length and parsability too much.

    timestamp = _unix_time()
    operation_name_lower = operation_name.lower()
    branch_name = "{operation_name_lower}-{timestamp}".format(**locals())
    tag_name = "{branch_name}-root".format(**locals())
    tag_refspec_pattern = "refs/tags/{operation_name_lower}-*-root".format(**locals())

    # As many things as possible are controlled for the commit, so the commitid
    # can be used for deduplication.
    yield from prepare_new_branch(expect_ok, repo_dir, branch_name, orphan=orphan)
    try:
        yield from fixed_date_commit(expect_ok, repo_dir, operation_name)
    except exception.CommandError as e:
        if no_change_ok and e.exit_code == 1:
            # No changes were made
            return None
        else:
            raise

    # Check if any root tag in the internal repo matches the commitid we currently have.
    # Note that this operation isn't atomic, but it won't matter too much if interleaving happens.
    # Worst case, you'll have multiple branch/root_tag pairs pointing at the same commit.
    existing_tag = yield from deduplicate_head_tag(expect_ok, repo_dir, tag_refspec_pattern)

    if existing_tag is None:
        yield from annotated_tag(expect_ok, repo_dir, tag_name, operation_description)
        yield from push_with_tags(expect_ok, repo_dir, branch_name)

        logger.info("Pushed branch {branch_name} to repo {repo_url}".format(**locals()))

        return {
            "branch": branch_name,
            "tag": tag_name,
            "url": repo_url,
        }

    # Discard new branch and use existing branch and tag
    else:
        # ex: proj-1.0_1436360795_root -> proj-1.0_1436360795
        existing_branch = existing_tag[:-5]

        # Have to be careful about this state if anything reuses the repo.
        # In the adjust scenario, the new branch it creates (from an identical
        # commitid) will isolate it from the discarded local branches made by
        # the pull.

        logger.info("Using existing branch {branch_name} in repo {repo_url}".format(**locals()))

        return {
            "branch": existing_branch,
            "tag": existing_tag,
            "url": repo_url,
        }
