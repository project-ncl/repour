import asyncio
import os
import subprocess
import tempfile
import unittest

import repour.asutil
import repour.asgit

loop = asyncio.get_event_loop()
expect_ok = repour.asutil.expect_ok_closure()

class TemporaryGitDirectory(tempfile.TemporaryDirectory):
    def __init__(self, bare=False):
        super().__init__()
        self.bare = bare

    def __enter__(self):
        cmd = ["git", "init"]
        if self.bare:
            cmd.append("--bare")
        cmd.append(self.name)
        quiet_check_call(cmd)
        return self.name

def quiet_check_call(cmd):
    return subprocess.check_call(cmd, stdout=subprocess.DEVNULL)

class TestCommon(unittest.TestCase):
    def test_setup_commiter(self):
        with TemporaryGitDirectory() as repo:
            loop.run_until_complete(repour.asgit.setup_commiter(expect_ok, repo))
            out = subprocess.check_output(["git", "-C", repo, "config", "--local", "-l"])

        self.assertIn(b"user.name=", out)
        self.assertIn(b"user.email=", out)

    def test_fixed_date_commit(self):
        with TemporaryGitDirectory() as repo:
            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello")
            quiet_check_call(["git", "-C", repo, "add", "-A"])
            loop.run_until_complete(repour.asgit.fixed_date_commit(expect_ok, repo, "Test"))
            out = subprocess.check_output(["git", "-C", repo, "log", "-1", "--pretty=fuller"])

        self.assertIn(b"AuthorDate: Thu Jan 1 00:00:00 1970 +0000", out)
        self.assertIn(b"CommitDate: Thu Jan 1 00:00:00 1970 +0000", out)

    def test_prepare_new_branch(self):
        with TemporaryGitDirectory() as repo:
            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello")
            loop.run_until_complete(repour.asgit.prepare_new_branch(expect_ok, repo, "pull-1234567890", orphan=True))
            quiet_check_call(["git", "-C", repo, "commit", "-m", "Test"])

            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello Hello")
            loop.run_until_complete(repour.asgit.prepare_new_branch(expect_ok, repo, "adjust-1234567890"))
            quiet_check_call(["git", "-C", repo, "commit", "-m", "Test"])

    def test_deduplicate_head_tag(self):
        with TemporaryGitDirectory() as remote:
            with open(os.path.join(remote, "asd.txt"), "w") as f:
                f.write("Hello")
            loop.run_until_complete(repour.asgit.prepare_new_branch(expect_ok, remote, "pull-1234567890", orphan=True))
            loop.run_until_complete(repour.asgit.fixed_date_commit(expect_ok, remote, "Pull"))

            with open(os.path.join(remote, "asd.txt"), "w") as f:
                f.write("Hello Hello")
            loop.run_until_complete(repour.asgit.prepare_new_branch(expect_ok, remote, "adjust-1234567890"))
            loop.run_until_complete(repour.asgit.fixed_date_commit(expect_ok, remote, "Adjust"))

            with TemporaryGitDirectory() as repo:
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello")
                loop.run_until_complete(repour.asgit.prepare_new_branch(expect_ok, repo, "pull-568757645", orphan=True))
                loop.run_until_complete(repour.asgit.fixed_date_commit(expect_ok, repo, "Pull"))

                existing_tag = loop.run_until_complete(repour.asgit.deduplicate_head_tag(expect_ok, repo, remote))
                self.assertEqual(existing_tag, "pull-1234567890")

                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello Hello")
                loop.run_until_complete(repour.asgit.prepare_new_branch(expect_ok, repo, "adjust-256462457"))
                loop.run_until_complete(repour.asgit.fixed_date_commit(expect_ok, repo, "Adjust"))

                existing_tag = loop.run_until_complete(repour.asgit.deduplicate_head_tag(expect_ok, repo, remote))
                self.assertEqual(existing_tag, "adjust-1234567890")

                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Goodbye")
                loop.run_until_complete(repour.asgit.prepare_new_branch(expect_ok, repo, "adjust-256462457"))
                loop.run_until_complete(repour.asgit.fixed_date_commit(expect_ok, repo, "Adjust"))

                existing_tag = loop.run_until_complete(repour.asgit.deduplicate_head_tag(expect_ok, repo, remote))
                self.assertIsNone(existing_tag)

    def test_annotated_tag(self):
        with TemporaryGitDirectory() as repo:
            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello")
            quiet_check_call(["git", "-C", repo, "add", "-A"])
            quiet_check_call(["git", "-C", repo, "commit", "-m", "Test"])
            loop.run_until_complete(repour.asgit.annotated_tag(expect_ok, repo, "pull-1234567890-root", "Annotation"))
            out = subprocess.check_output(["git", "-C", repo, "tag", "-l", "-n"])

        self.assertIn(b"pull-1234567890-root Annotation", out)

    def test_push_with_tags(self):
        with TemporaryGitDirectory(bare=True) as remote:
            with TemporaryGitDirectory() as repo:
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Goodbye")
                quiet_check_call(["git", "-C", repo, "add", "-A"])
                quiet_check_call(["git", "-C", repo, "commit", "-m", "Test Commit"])
                quiet_check_call(["git", "-C", repo, "tag", "test-tag"])
                quiet_check_call(["git", "-C", repo, "remote", "add", "origin", remote])

                loop.run_until_complete(repour.asgit.push_with_tags(expect_ok, repo, "master"))

                remote_tags = subprocess.check_output(["git", "-C", repo, "tag", "-l", "-n"])

        self.assertIn(b"test-tag Test Commit", out)


class TestNewDedupBranch(unittest.TestCase):
    def test_unix_time(self):
        pass

    def test_(self):
        with TemporaryGitDirectory() as repo:
            pass
