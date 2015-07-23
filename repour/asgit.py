import asyncio

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
def deduplicate_head_tag(expect_ok, repo_dir, refspec_pattern="refs/tags/*"):
    head_commitid = yield from expect_ok(
        cmd=["git", "-C", repo_dir, "rev-parse", "HEAD"],
        desc="Could not get HEAD commitid with git",
        stdout="single",
    )
    stdout_lines = yield from expect_ok(
        cmd=["git", "ls-remote", internal_repo_url, tag_refspec_pattern],
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
        cmd=["git", "-C", dirname, "tag", "-a", "-m", message, tag_name],
        desc="Could not add tag with git",
    )

@asyncio.coroutine
def push_with_tags(expect_ok, repo_dir, branch_name):
    yield from expect_ok(
        cmd=["git", "-C", dirname, "push", "--atomic", "--follow-tags", "origin", branch_name],
        desc="Could not push tag+branch with git",
    )
