import asyncio
import datetime
import os
import subprocess
import unittest

import repour.asutil
import repour.asgit
from test import util

loop = asyncio.get_event_loop()
expect_ok = repour.asutil.expect_ok_closure()

class TestCommon(unittest.TestCase):
    def test_setup_commiter(self):
        with util.TemporaryGitDirectory() as repo:
            loop.run_until_complete(repour.asgit.setup_commiter(expect_ok, repo))
            out = subprocess.check_output(["git", "-C", repo, "config", "--local", "-l"])

        self.assertIn(b"user.name=", out)
        self.assertIn(b"user.email=", out)

    def test_fixed_date_commit(self):
        with util.TemporaryGitDirectory() as repo:
            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello")
            util.quiet_check_call(["git", "-C", repo, "add", "-A"])
            loop.run_until_complete(repour.asgit.fixed_date_commit(expect_ok, repo, "Test"))
            out = subprocess.check_output(["git", "-C", repo, "log", "-1", "--pretty=fuller"])

        self.assertIn(b"AuthorDate: Thu Jan 1 00:00:00 1970 +0000", out)
        self.assertIn(b"CommitDate: Thu Jan 1 00:00:00 1970 +0000", out)

    def test_prepare_new_branch(self):
        with util.TemporaryGitDirectory() as repo:
            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello")
            loop.run_until_complete(repour.asgit.prepare_new_branch(expect_ok, repo, "pull-1234567890", orphan=True))
            util.quiet_check_call(["git", "-C", repo, "commit", "-m", "Test"])

            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello Hello")
            loop.run_until_complete(repour.asgit.prepare_new_branch(expect_ok, repo, "adjust-1234567890"))
            util.quiet_check_call(["git", "-C", repo, "commit", "-m", "Test"])

    def test_annotated_tag(self):
        with util.TemporaryGitDirectory() as repo:
            with open(os.path.join(repo, "asd.txt"), "w") as f:
                f.write("Hello")
            util.quiet_check_call(["git", "-C", repo, "add", "-A"])
            util.quiet_check_call(["git", "-C", repo, "commit", "-m", "Test"])
            loop.run_until_complete(repour.asgit.annotated_tag(expect_ok, repo, "pull-1234567890-root", "Annotation"))
            out = subprocess.check_output(["git", "-C", repo, "tag", "-l", "-n"])

        self.assertIn(b"pull-1234567890-root Annotation", out)

    def test_push_with_tags(self):
        with util.TemporaryGitDirectory(bare=True) as remote:
            with util.TemporaryGitDirectory(origin=remote) as repo:
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Goodbye")
                util.quiet_check_call(["git", "-C", repo, "add", "-A"])
                util.quiet_check_call(["git", "-C", repo, "commit", "-m", "Test Commit"])
                util.quiet_check_call(["git", "-C", repo, "tag", "test-tag"])

                loop.run_until_complete(repour.asgit.push_with_tags(expect_ok, repo, "master"))

                remote_tags = subprocess.check_output(["git", "-C", repo, "tag", "-l", "-n"])

        self.assertIn(b"test-tag        Test Commit", remote_tags)


class TestPushNewDedupBranch(unittest.TestCase):
    def test_normal(self):
        with util.TemporaryGitDirectory(bare=True, ro_url="fake-ro-url") as remote:
            with util.TemporaryGitDirectory(origin=remote.readwrite) as repo:
                # Simulated pull
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello")
                p = loop.run_until_complete(repour.asgit.push_new_dedup_branch(
                    expect_ok=expect_ok,
                    repo_dir=repo,
                    repo_url=remote,
                    operation_name="Pull",
                    operation_description="Blah",
                    orphan=True,
                ))
                self.assertEqual(
                    first=p,
                    second={
                        "tag": "repour-0fe965e93b0cf7c91b9d44c14d9847e459c465c2",
                        "url": {
                            "readwrite": remote.readwrite,
                            "readonly": "fake-ro-url",
                        },
                    },
                )

                # No changes
                nc = loop.run_until_complete(repour.asgit.push_new_dedup_branch(
                    expect_ok=expect_ok,
                    repo_dir=repo,
                    repo_url=remote,
                    operation_name="Adjust",
                    operation_description="Bleh",
                    no_change_ok=True,
                ))
                self.assertIsNone(nc)

            with util.TemporaryGitDirectory(
                origin=remote.readwrite,
                ref="repour-0fe965e93b0cf7c91b9d44c14d9847e459c465c2",
            ) as repo:
                # Changes
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello Hello")
                c = loop.run_until_complete(repour.asgit.push_new_dedup_branch(
                    expect_ok=expect_ok,
                    repo_dir=repo,
                    repo_url=remote,
                    operation_name="Adjust",
                    operation_description="Bleh",
                    no_change_ok=True,
                ))
                self.assertIsNotNone(c)
                self.assertIn("tag", c)
                self.assertIn("repour", c["tag"])
                self.assertIn("url", c)
                self.assertEqual(remote.readwrite, c["url"]["readwrite"])
                self.assertEqual("fake-ro-url", c["url"]["readonly"])

            with util.TemporaryGitDirectory(
                origin=remote.readwrite,
                ref="repour-0fe965e93b0cf7c91b9d44c14d9847e459c465c2",
            ) as repo:
                # Changes, already existing
                with open(os.path.join(repo, "asd.txt"), "w") as f:
                    f.write("Hello Hello")
                ce = loop.run_until_complete(repour.asgit.push_new_dedup_branch(
                    expect_ok=expect_ok,
                    repo_dir=repo,
                    repo_url=remote,
                    operation_name="Adjust",
                    operation_description="Bleh",
                    no_change_ok=True,
                ))
                self.assertIsNotNone(ce)
                self.assertEqual(ce, c)
