# flake8: noqa
import asyncio
import datetime
import os
import subprocess
import tempfile
import time
import unittest
from test import util

from repour.lib.scm import git
import repour.asutil

loop = asyncio.get_event_loop()
expect_ok = repour.asutil.expect_ok_closure()


class TestGit(unittest.TestCase):
    def test_is_ref_a_pull_request(self):
        self.assertTrue(git.is_ref_a_pull_request("merge-requests/1"))
        self.assertTrue(git.is_ref_a_pull_request("merge-requests/45"))
        self.assertTrue(git.is_ref_a_pull_request("merge-requests/80"))

        self.assertTrue(git.is_ref_a_pull_request("pull/1"))
        self.assertTrue(git.is_ref_a_pull_request("pull/45"))
        self.assertTrue(git.is_ref_a_pull_request("pull/80"))

        self.assertFalse(git.is_ref_a_pull_request("2.1.0.Final"))
        self.assertFalse(git.is_ref_a_pull_request("temporary-myself"))

    def test_modify_ref_to_be_fetchable(self):
        modified, branch = git.modify_ref_to_be_fetchable("not-a-pr")

        self.assertIsNone(modified)
        self.assertIsNone(branch)

        ref = "merge-requests/60"
        modified, branch = git.modify_ref_to_be_fetchable(ref)

        self.assertEqual(modified, ref + "/head:" + branch)

        ref = "pull/3"
        modified, branch = git.modify_ref_to_be_fetchable(ref)

        self.assertEqual(modified, ref + "/head:" + branch)

    def test_git_lfs_attributes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with open(temp_dir + "/.gitattributes", "w") as f:
                f.write("*.onnx filter=lfs diff=lfs merge=lfs -text\n")

            self.assertTrue(git.is_repository_using_lfs(temp_dir))

        with tempfile.TemporaryDirectory() as temp_dir:
            with open(temp_dir + "/.gitattributes", "w") as f:
                f.write("happy little git attributes")

            self.assertFalse(git.is_repository_using_lfs(temp_dir))

        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertFalse(git.is_repository_using_lfs(temp_dir))
