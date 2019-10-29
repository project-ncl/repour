import asyncio
import datetime
import os
import subprocess
import time
import unittest
from test import util

import repour.asgit
import repour.asutil

loop = asyncio.get_event_loop()
expect_ok = repour.asutil.expect_ok_closure()


class TestCommon(unittest.TestCase):
    def test_setup_commiter(self):
        with util.TemporaryGitDirectory() as repo:
            loop.run_until_complete(repour.asgit.setup_commiter(expect_ok, repo))
            out = subprocess.check_output(["git", "config", "--local", "-l"], cwd=repo)

        self.assertIn(b"user.name=", out)
        self.assertIn(b"user.email=", out)

    def test_fixed_date_commit(self):
        with util.TemporaryGitDirectory() as repo:
            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello")
            util.quiet_check_call(["git", "add", "-A"], cwd=repo)
            loop.run_until_complete(
                repour.asgit.fixed_date_commit(expect_ok, repo, "Test")
            )
            out = subprocess.check_output(
                ["git", "log", "-1", "--pretty=fuller"], cwd=repo
            )

        self.assertIn(b"AuthorDate: Thu Jan 1 00:00:00 1970 +0000", out)
        self.assertIn(b"CommitDate: Thu Jan 1 00:00:00 1970 +0000", out)

    def test_prepare_new_branch(self):
        with util.TemporaryGitDirectory() as repo:
            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello")
            loop.run_until_complete(
                repour.asgit.prepare_new_branch(
                    expect_ok, repo, "pull-1234567890", orphan=True
                )
            )
            util.quiet_check_call(["git", "commit", "-m", "Test"], cwd=repo)

            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello Hello")
            loop.run_until_complete(
                repour.asgit.prepare_new_branch(expect_ok, repo, "adjust-1234567890")
            )
            util.quiet_check_call(["git", "commit", "-m", "Test"], cwd=repo)

    def test_annotated_tag(self):
        with util.TemporaryGitDirectory() as repo:
            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello")
            util.quiet_check_call(["git", "add", "-A"], cwd=repo)
            util.quiet_check_call(["git", "commit", "-m", "Test"], cwd=repo)
            loop.run_until_complete(
                repour.asgit.annotated_tag(
                    expect_ok, repo, "pull-1234567890-root", "Annotation"
                )
            )
            out = subprocess.check_output(["git", "tag", "-l", "-n"], cwd=repo)

        self.assertIn(b"pull-1234567890-root Annotation", out)

    def test_push_with_tags(self):
        with util.TemporaryGitDirectory(bare=True) as remote:
            with util.TemporaryGitDirectory(origin=remote) as repo:
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Goodbye")
                util.quiet_check_call(["git", "add", "-A"], cwd=repo)
                util.quiet_check_call(["git", "commit", "-m", "Test Commit"], cwd=repo)
                util.quiet_check_call(["git", "tag", "test-tag"], cwd=repo)

                loop.run_until_complete(
                    repour.asgit.push_with_tags(expect_ok, repo, "master")
                )

                remote_tags = subprocess.check_output(
                    ["git", "tag", "-l", "-n"], cwd=repo
                )

        self.assertIn(b"test-tag        Test Commit", remote_tags)


class TestPushNewDedupBranch(unittest.TestCase):
    def test_normal(self):
        with util.TemporaryGitDirectory(bare=True, ro_url="fake-ro-url") as remote:

            tag = None

            with util.TemporaryGitDirectory(origin=remote.readwrite) as repo:
                # Simulated pull
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello")
                p = loop.run_until_complete(
                    repour.asgit.push_new_dedup_branch(
                        expect_ok=expect_ok,
                        repo_dir=repo,
                        repo_url=remote,
                        operation_name="Pull",
                        operation_description="Blah",
                        orphan=True,
                        real_commit_time=True,
                    )
                )
                self.assertEqual(p["url"]["readwrite"], remote.readwrite)
                self.assertEqual(p["url"]["readonly"], "fake-ro-url")

                tag = p["tag"]

                time.sleep(2)

                # No changes
                nc = loop.run_until_complete(
                    repour.asgit.push_new_dedup_branch(
                        expect_ok=expect_ok,
                        repo_dir=repo,
                        repo_url=remote,
                        operation_name="Adjust",
                        operation_description="Bleh",
                        no_change_ok=True,
                        force_continue_on_no_changes=True,
                        real_commit_time=True,
                    )
                )

            with util.TemporaryGitDirectory(origin=remote.readwrite, ref=tag) as repo:
                # Changes
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello Hello")
                c = loop.run_until_complete(
                    repour.asgit.push_new_dedup_branch(
                        expect_ok=expect_ok,
                        repo_dir=repo,
                        repo_url=remote,
                        operation_name="Adjust",
                        operation_description="Bleh",
                        no_change_ok=True,
                        force_continue_on_no_changes=True,
                        real_commit_time=True,
                    )
                )
                self.assertIsNotNone(c)
                self.assertIn("tag", c)
                self.assertIn("repour", c["tag"])
                self.assertIn("url", c)
                self.assertEqual(remote.readwrite, c["url"]["readwrite"])
                self.assertEqual("fake-ro-url", c["url"]["readonly"])

            with util.TemporaryGitDirectory(origin=remote.readwrite, ref=tag) as repo:
                # Changes, already existing
                # Sleep to make sure commit date are different, if duplicate commit generated
                time.sleep(5)
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello Hello")
                ce = loop.run_until_complete(
                    repour.asgit.push_new_dedup_branch(
                        expect_ok=expect_ok,
                        repo_dir=repo,
                        repo_url=remote,
                        operation_name="Adjust",
                        operation_description="Bleh",
                        no_change_ok=True,
                        force_continue_on_no_changes=True,
                        real_commit_time=True,
                    )
                )
                self.assertIsNotNone(ce)
                self.assertEqual(ce, c)
